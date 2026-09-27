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

## 真实数据运行记录（2026-09，首次全量跑）

首轮真实采集 21 个源 → 430 条新文档；随后用 deepseek-flash 处理。踩到并修掉的问题：

1. **串行太慢**：实测约 5.4s/文档，430 条要 40 分钟。改为 `asyncio.Semaphore` 并发（`LLM_CONCURRENCY`，默认 5），先并发调模型、再顺序落库。
2. **并发批次死锁（实测 `deadlock detected`）**：一次 `SELECT … FOR UPDATE` 锁住几百条文档、并把事务开到最后，与 worker 的另一批在 `llm_usage` 那一行上互相等待。修法两层：
   - `run_process` 分小块（默认 10 条）处理，**块之间提交**，锁只持有十几秒；
   - `_record_usage` 改成 `INSERT … ON CONFLICT DO UPDATE` 累加，不再"先查后写"。
3. **取待处理文档加行锁**：`with_for_update(skip_locked=True)`，让并发的两个执行者跳过彼此已占用的行，避免同一文档被重复调用付费接口。
4. **只有标题的条目**（GDELT）：新增 `headline` 提示词 + `headline-only` 标签，要求摘要以"（仅据标题）"开头、禁止补细节；标题太短（<15 字）仍直接拒绝。
5. **过期内容**：新增 `max_item_age_days`（默认 45 天），发布早于阈值的内容记 `rejected/too_old`，用来挡住"200 但内容是几年前的静态 XML"的源。
6. **成本可观测**：`llm_usage` 记录 calls/tokens；单价靠环境变量注入。首轮 430 条的 token 量级是"几万输入/几万输出"，据此可估算日成本。

### 已知局限（Phase 2 处理）

- 单进程内并发；多个 worker 副本仍会互相抢同一批（有 `skip_locked` 兜底，但吞吐不会叠加）。
- 处理进度不可中断续跑：批次中途重启会让本批的 LLM 花费白费（已写入的 analysis 会保留，状态机保证不会重复计费同一条）。
- 日报/周报尚未接入，Feed 是当前唯一出口。

### 向量提供方的实测对比（同一批 430 条真实数据）

| 配置 | 聚类总数 | 多文档聚类 | 最大聚类 |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER=hash`（无 ML 依赖） | 322 | **1** | 2 |
| `EMBEDDING_PROVIDER=local`（paraphrase-multilingual-MiniLM-L12-v2） | 305 | **10** | 6 |

local 下聚到的事件都跨了多个来源，例如"南非枪击"6 条来自 6 个源、"伊朗/霍尔木兹"5 条来自 4 个源、
"瑞士中立公投"3 条来自 3 个源——这才是"同一事件多来源覆盖"的可用形态。

结论与约定：

- **生产必须用 `local`**：`hash` 只保证链路可跑通，语义聚类实际失效；
  API 在生产环境检测到 `hash` 时会打 `embedding.hash_in_production` 警告。
- `uv sync --extra ml`（或 `make ml`）装 sentence-transformers；CI 不装，保持快与省。
- 切换提供方或调整阈值后用 `make reembed` 重算向量与聚类（幂等，会重建 embeddings/clusters）。
- 模型权重默认落在 `~/.cache/huggingface`，受限沙箱下会被拒绝；Makefile 已把 `HF_HOME`/`TORCH_HOME` 一并重定向到仓库内 `.cache/`。