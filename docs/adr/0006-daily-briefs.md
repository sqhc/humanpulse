# ADR-0006：日报的生成方式（结构化 JSON + 服务端渲染）

- 状态：已接受（周报部分待实现）
- 日期：2026-09
- 决策者：sqhc

## 背景

平台的价值主张是"每天用几分钟读完当天值得记录的事"。Feed 只能一条条看，需要一份聚合产物：日报（后续还有周报）。
难点在于：日报既要**双语**，又要**可复现**、**不编造链接**，还要能在不额外花钱的前提下换语言重看。

## 决策

1. **模型只输出结构化 JSON**（`BriefContent`：标题/概述/分组/要点，中英各一份），**Markdown 由我们自己渲染**（`app/briefs/render.py`）。
   - 好处：同一份内容可以零成本重渲染成中/英 Markdown；渲染结果可测试；来源清单由我们按素材拼，模型没有机会编造链接。
   - 代价：提示词更长（要解释字段结构），且模型输出需要一次 Pydantic 校验。
2. **素材 = 按 cluster 去重后的 Top N**（默认 12 条）：同一事件只留评分最高的一条代表，避免头条被同一事件刷屏。
3. **幂等**：默认同一天只生成一次（`_existing_brief_id`）；`force=True` 用于重跑（运维命令与冒烟测试用）。
4. **没有素材也要留痕**：写一条 `reason=no_items` 的占位简报，而不是静默跳过——否则"今天没更新"和"任务挂了"无法区分。
5. **分段固定**：conflict / science / labor / other，与平台三个长期议题一致；没有素材的分组直接省略。
6. **入口**：`POST /api/v1/admin/jobs/brief/run`（管理员）、`make brief`、以及 worker 到 `BRIEF_HOUR` 之后每 15 分钟探一次（生成函数幂等，所以探多次是安全的）。

## 数据

- `briefs`：`kind(daily|weekly)`、`period_start/end`、`language`、`title`、`markdown`（zh 版，便于直接读）、`structured`（完整双语 JSON）、`model`、`prompt_version`、`cost_usd`。
- `brief_items`：`rank` + `document_id` + `cluster_id`，保留"这一期用了哪些素材"，便于回溯与重渲染来源清单。
- 迁移：`d86d2e05f291_phase_2_briefs`（up/down 均已验证）。

## 后果

- 日报质量上限取决于选材：目前只按评分排序，没有"与昨天相比的新颖度"衰减。周报与"新颖度排序"留到下一轮。
- 素材摘要已经是双语，所以日报的双语不需要额外翻译调用（一次调用同时产出中英）。
- 若模型返回的 JSON 无法通过校验，`complete_json` 会带着错误摘要重试一次；两次都失败则整批抛出，已有数据不受影响。

## 待办（周报，Phase 2 后续）

1. 复用同一套 `select → complete_json → render`，窗口改为 7 天，并把 `kind="weekly"`；
2. 周报需要趋势信息（话题频次变化、实体共现），这部分用 SQL 算好再喂给模型，而不是让模型自己数；
3. 需要"与上一期的差异"时，用 cluster 的 `first_seen_at` 做新颖度排序。
