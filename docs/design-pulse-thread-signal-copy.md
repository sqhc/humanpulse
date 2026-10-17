# Pulse / Thread / Signal · 视图文案内核

> 上游文档：[design-pulse-tweet-copy.md](design-pulse-tweet-copy.md)（tweet 模板 + 钩子三律）。
> 本文定义三个视图的**微文案**：标签、徽标、空态、解释行。
> 铁律：**解释性文案一律是数据槽位拼接（确定性），禁止模型现场生成**——与「来源清单由服务端拼」同一条红线。涉及模型生成的叙事必须带「AI 生成」标注。

## 诚实边界（三视图通用）

1. 不出现概率、不预测走向（未过门的能力不进任何文案）。
2. 解释行只用可计算的事实槽位：条数、时间间隔、来源数、语种、首见时间。
3. 立场性判断只允许出现在 tweet 钩子（走钩子三律审稿），微文案层不判断。
4. 双语同构：zh/en 文案一一对应，槽位一致。

---

## Pulse（实时脉搏）· 微文案

**强度档**（由「近 N 小时报道数」分档，确定性计算）：

| 档位 | zh | en | 判定 |
|---|---|---|---|
| 平稳 | 平稳 | steady | 近 6h ≤2 条 |
| 升温 | 升温中 | heating up | 近 6h 3–5 条且递增 |
| 高热 | 高热 | hot | 近 6h ≥6 条 |
| 降温 | 降温中 | cooling down | 有报道但近 6h 0 条 |

**脉搏卡一行**（卡头，槽位拼接）：

```
zh: {事件短语} · {N} 条报道 · 最近 {H} 小时 · {强度档}
en: {event phrase} · {N} reports · last {H}h · {intensity}
```

**空态**（冷启动/深夜无事件）：

> zh：现在很安静。脉搏在事件发酵时才会亮起。
> en：All quiet. Pulses light up when events start moving.

**SSE 浮层**（新文档进入已展示的 cluster）：

> zh：{事件短语} 有新进展（+1）
> en：New development in {event phrase} (+1)

---

## Thread（事件脉络）· 微文案

**章节标签**（按确定性规则分章，不做语义判断）：

| 章节 | zh | en | 判定（确定性） |
|---|---|---|---|
| 首报 | 首报 | First report | cluster 第一条 |
| 进展 | 进展 | Developments | 后续连续报道 |
| 重启 | 沉寂后重启 | Back in play | 间隔 ≥24h 后出现新条目 |
| 现状 | 最新 | Latest | 最新一条 |

> 「转折/反转」是语义判断，**微文案层不设此章节**；若未来由模型标注叙事转折，必须带「AI 生成」标注并单独评审。

**脉络头**：

```
zh: {事件名} · {N} 条报道 · 跨度 {D} 天 · {M} 个来源
en: {event} · {N} reports · {D}-day span · {M} sources
```

**章节间过渡行**（可选，仅重启章节用——因为它是可计算的事实）：

> zh：沉默 {X} 天后，这条线重新动了起来。
> en：After {X} quiet days, this line is moving again.

**脉络小结**（Phase 2，模型生成时才启用，带标注）：

> zh：以下事件演化小结由 AI 生成，仅供参考，请以各条原文为准。
> en：The evolution summary below is AI-generated; refer to the linked originals.

---

## Signal（信噪比）· 「这是真正新的」提示语

Signal 的全部文案都回答一个问题：**为什么这条出现在你面前**。答案只允许来自确定性槽位。

**新在哪徽标**（每条前置，四选一，按优先级）：

| 类型 | zh | en | 触发（确定性） |
|---|---|---|---|
| 新事件 | 新事件 · {时间} 首报 | New event · first seen {time} | 新 cluster 首条 |
| 跨语种 | 新增{语种}来源首报 | First {language}-language source | cluster 首次出现新语种 |
| 来源扩展 | 来源扩展至 {M} 家 | Now covered by {M} outlets | 来源数跨档（如 3→6） |
| 重启 | 沉寂 {X} 天后重启 | Resumed after {X} quiet days | 间隔 ≥24h 的新条目 |

**折叠徽标**（被合并的重复报道）：

> zh：已折叠 {N} 条同事件报道
> en：{N} duplicate reports folded
> tooltip zh：同一事件的多来源报道已合并；点开看全部来源与各自原文链接。
> tooltip en：Multiple outlets covering the same event are merged; open to see every source link.

**Feed 头降噪行**（本页汇总，槽位拼接）：

```
zh: 本页 {shown} 条 = {new} 条新信息 + {folded} 条已折叠重复
en: This page: {shown} items = {new} novel + {folded} folded duplicates
```

**关闭降噪时**（尊重用户选择，不说教）：

> zh：降噪已关闭——显示全部 {total} 条，含重复报道。
> en：Noise filter off — showing all {total} items, duplicates included.

---

## 反例（文案层不许出现的写法）

- ❌ 「这条比昨天更重要」（重要性是判断，且无数据支撑）
- ❌ 「预计事态将升级」（预测，违反诚实边界）
- ❌ 「多家权威媒体证实」（「权威」是立场；只写来源数：{M} 家）
- ❌ 「AI 认为该事件值得关注」（把模型判断伪装成事实）

—— 写手 · 2026-10-17
