# ADR-0003：AI 处理流水线与成本策略

- 状态：已接受
- 日期：2026-01
- 决策者：sqhc

## 背景

处理层是平台核心价值，也是主要成本与质量风险来源：既要双语摘要与重要性评分，又要避免为转载内容重复付费。

## 决策

### 固定流水线

`normalize → 语言识别 → SimHash 去重 → LLM 富化 → 向量化 → 向量去重/聚类 → 入库`

每一步幂等、可重跑、可断点续跑，状态记录在 `documents.status`。

### 模型与调用

- **直连 DeepSeek API**（OpenAI 兼容）：`base_url=https://api.deepseek.com`。
- 模型名与单价全部走 env：`LLM_MODEL_BULK`（评分/摘要）、`LLM_MODEL_BRIEF`（日报/周报）。实施时以 provider 的 `/models` 返回为准，不在代码中硬编码。
- 一次调用返回严格 JSON：相关性、中英双语摘要、标签、地区、0–100 重要性评分、评分理由、实体提及。
- 输出用 Pydantic 校验；失败先做一次"修复重试"，再失败落入 `rejected` 并记录原因，不阻塞批次。
- 与平台主题无关的内容评 0 分不入库，但保留 `documents` 行以便审计过滤质量。

### 提示词管理

- 按内容类型分文件：`news.md`（事实、影响、各方立场）、`discussion.md`（提炼分歧而非站队）、`report.md`（机构报告的方法与结论）。
- 每份提示词带版本号，写入 `analyses.prompt_version`；改动必须升版本，便于回溯"这条摘要当时用的哪版"。

### 成本控制

1. SimHash 前置拦截（汉明距离 ≤3 视为重复），在调用 LLM 之前省掉转载与镜像。
2. `content_hash` 结果缓存，重复内容直接复用分析结果。
3. 单 run token 预算（`LLM_DAILY_TOKEN_BUDGET`）；超预算自动降级为"仅元数据入库，摘要排队"。
4. 全部调用写 `llm_usage` 台账（tokens、成本、调用数），`scripts/report_cost.py` 输出每日成本。

### 向量与去重

- **DeepSeek API 不提供 embeddings 端点**，向量必须本地或第三方计算。
- 本地模型默认 `paraphrase-multilingual-MiniLM-L12-v2`（中英混合语料显著优于英文中心的 all-MiniLM-L6-v2），可选 `BAAI/bge-m3`。
- 存 pgvector（HNSW，cosine）。阈值：默认 0.85，24 小时内的热点内容放宽到 0.80；两者均可配置。
- 近邻合并用并查集，24 小时时间窗；cluster 内保留评分最高者为 canonical。

### 评分的主观性

重要性评分是模型判断，不是事实。因此：保留 `score_rationale`、记录模型与提示词版本、Phase 2 提供人工覆盖入口。

## 后果

- 早于 LLM 的去重省 token，但也可能误杀改写幅度大的同源报道——用 `rejection_reason` 保留可审计痕迹，阈值可调。
- 聚类以"最先入库且评分最高者为 canonical"起步；评分变化后的重选举留到 Phase 2。

## 实施记录（Phase 1）

1. **模型名以实测为准**：`GET https://api.deepseek.com/models` 返回 `deepseek-flash`（V4.1-Flash，1M 上下文，支持图片输入）与 `deepseek-v4-pro`（V4-Pro）。文档初稿里的 `deepseek-chat`/`deepseek-reasoner` 已全部替换。单价不硬编码，用 `DEEPSEEK_PRICE_IN`/`DEEPSEEK_PRICE_OUT` 注入，未填则成本记 0。
2. **向量提供方做成可切换**：`EMBEDDING_PROVIDER=hash` 用确定性哈希向量，无需下载模型，供开发/CI 使用；`local` 才是多语种 sentence-transformers 模型（需 `uv sync --extra ml`）。CI 冒烟固定用 `hash` + `LLM_PROVIDER=fake`，因此**CI 不联网、不产生费用**。hash 向量没有语义能力，不能据此评估去重质量——阈值标定必须在 `local` 下做。
3. **实体表延后**：`entities`/`entity_mentions` 暂不建表，实体先以 JSONB 存在 `analyses.entities`；等 Phase 3 做实体时间线时再拆表并回填。这样避免在实体归一规则未定时锁死 schema。
4. **不引入 APScheduler**：Phase 1 只需要固定间隔语义，worker 用内置 asyncio 循环实现（`app/workers/scheduler.py`），少一个依赖、行为可测；需要 cron 表达式或分布式调度时再替换。
5. **SimHash 候选集在 Python 内比对**：只取近 3 天、最多 5000 条指纹。数据量上去后需改成数据库侧 popcount 或专用索引，否则会成为瓶颈。
