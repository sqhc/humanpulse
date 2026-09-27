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

- 需要本地算力（首次会下载数百 MB 模型）；`ml` 依赖组按需安装。
- 早于 LLM 的去重省 token，但也可能误杀改写幅度大的同源报道——用 `rejection_reason` 保留可审计痕迹，阈值可调。
