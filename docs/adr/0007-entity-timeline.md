# ADR-0007：实体时间线（把 JSONB 里的实体拆成表）

- 状态：已接受
- 日期：2026-09
- 决策者：sqhc

## 背景

Phase 1 起，LLM 为每条分析输出实体数组（人物/组织/地点/事件），但当时只存进 `analyses.entities` 这个 JSONB，
理由是"实体归一规则未定之前不锁死 schema"（见 ADR-0003 第 3 条）。
现在需要回答"某个国家/人物/组织最近被怎么提及"，JSONB 无法索引、无法按天聚合，于是拆表。

## 决策

1. **两张表**：
   - `entities`：`key`（唯一）、`name`、`kind(person|org|place|event)`、`aliases[]`、`mention_count`、`first_seen_at`、`last_seen_at`、`wikidata_id`（预留）。
   - `entity_mentions`：`entity_id` + `document_id`（联合唯一）+ `analysis_id` + `salience`。
2. **归一化只做同形合并**：NFKC → 小写 → 去掉中文之间的空格 → 去标点 → 压空白；`key = kind:归一化名字`。
   - 因此 `U.S.` 与 `us`、`Donald  Trump` 与 `donald trump` 会合并；
   - **`中国` 与 `China`、`特朗普` 与 `Donald Trump` 不会合并**——跨语言别名需要人工别名表或 Wikidata 支持，`wikidata_id` 列先留出位置。
3. **只有通过相关性筛选的文档才写入实体**，避免噪音实体污染时间线。
4. **历史数据用 `make backfill-entities` 回填**（幂等）：读 `analyses.entities` 重新入库，不删 JSONB（保留原始输出便于审计）。
5. **接口**：`GET /entities?q=&kind=&order=mentions|recent`、`GET /entities/{id}?days=&recent_limit=`（返回按天聚合的时间线 + 最近提及的文档）。

## 实测

对已有的 445 条分析回填：444 条有实体，共写入 2243 条提及。Top 实体：

| 实体 | 类型 | 提及 |
| --- | --- | --- |
| United States | place | 77 |
| Donald Trump | person | 50 |
| China | place | 40 |
| Xi Jinping | person | 32 |
| 中国 | place | 30 |

注意最后两行的对比：`China`(40) 与 `中国`(30) 是两条记录——这正是第 2 条决策的代价，也是下一步要做别名表的原因。

## 后果

- 时间线目前只按天计数，没有做"实体共现"（哪些实体总一起出现）——周报趋势后续要用到。
- `mention_count` 是累加计数；如果回填重复执行，因为 mentions 有唯一约束，不会重复计数（幂等）。
- 删除文档会级联删除提及；删除分析会把 `analysis_id` 置空但保留提及。
