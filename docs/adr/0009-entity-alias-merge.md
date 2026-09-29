# ADR-0009：实体别名合并（中国 / China 是一条）

- 状态：已接受
- 日期：2026-09
- 决策者：sqhc

## 背景

实体时间线上线后发现一个明显问题：**同一个实体被拆成多条记录**。真实数据（2243 条提及）里：

| 合并前 | 提及 | 合并前 | 提及 |
| --- | --- | --- | --- |
| United States | 77 | 美国 | 29 |
| China | 40 | 中国 | 30 |
| Donald Trump | 50 | 特朗普 / 川普 / Trump | 21 |

归一化（ADR-0007 第 2 条）只做同形合并（大小写、全角、标点），跨语言写法必须靠人工知识或外部知识库。

## 决策

1. **人工别名表随应用发布**：`backend/app/entity_aliases.yaml`（31 组，国家/地区/人物/组织）。
   放在 `app/data` 而不是 `infra/seed`：别名是**应用知识**（决定对外展示的实体是谁），必须随镜像发布；
   `infra/seed` 放环境相关的种子数据（数据源）。可用 `ENTITY_ALIAS_FILE` 覆盖路径。
2. **合并方式**：`entities.canonical_entity_id`（自引用外键）。合并时：
   - 把别名实体的 `entity_mentions` **改指向规范实体**（同一文档两条提及只保留一条），
   - 别名行保留（`mention_count=0`、`canonical_entity_id` 指向规范实体）用于审计，
   - 规范实体的 `mention_count` 按实际提及数重算，别名写法进入 `aliases` 字段。
   查询侧只需要 `WHERE canonical_entity_id IS NULL`，API 保持简单。
3. **写入时就合并**：`upsert_entities` 先查别名表（`resolve_alias`），新内容直接落到规范实体上；
   否则每轮处理都会把时间线重新拆开。
4. **提供候选发现**：`make entity-candidates` 列出"同类型 + 同文档共现 ≥2 次 + 一个中文名一个拉丁名"的候选对，
   供人工确认后写进 YAML——不自动合并。
5. **不接 Wikidata 自动合并**（当前）：消歧风险真实存在（`苹果` 是水果还是公司、`Mercury` 是行星还是人名），
   而**错误合并比漏合并更糟**——它会把两个实体的事件混成一条时间线。`entities.wikidata_id` 先留位。

## 实测效果

```
{"groups": 31, "merged": 18, "promoted": 1, "moved": 128, "dropped": 0, "missing": 1}
```

合并后 Top 实体：United States(106, 含 美国)、China(71, 含 中国/中华人民共和国)、
Donald Trump(71, 含 特朗普/川普)、Xi Jinping(46, 含 习近平)。

`dropped: 0` 说明没有出现"同一文档里两种写法都提到"的冲突；`missing: 1` 是某个组在库里还没有出现过。

## 后果

- **合并是可复现的**：`analyses.entities`（JSONB）保留了模型原始输出，重跑 `backfill-entities` + `alias-apply` 就能重建；
  但 `alias-apply` 本身是单向的（改指向之后无法自动还原到拆分状态）。
- `entities.mention_count` 只在合并/写入时维护；如果要严格对账，用 `count(entity_mentions)` 复核。
- 别名表需要人工维护（新增热门实体时要补），`entity-candidates` 是降低维护成本的工具，不是替代品。
- 待办：管理台里加"候选确认"界面，把 YAML 的编辑也搬到界面上。
