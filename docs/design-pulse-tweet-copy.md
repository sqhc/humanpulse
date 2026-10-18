# Tweet 式短讯 · 文案模板与钩子样例

> 用途：Week 1「双语脉搏卡」的文案层规范。每条 = **一句话事实 + 一个钩子**。
> 钩子分两拍：先「为什么重要」（一句判断），再「接下来看什么」（一个可核验的观察点）。
> 与短摘要的区别：摘要复述内容，脉搏卡给读者**一个继续看下去的理由**。

## 硬约束

| 约束 | 值 | 校验方式 |
|---|---|---|
| 总长 | ≤280 字符（含标签与换行，zh/en 同限） | 渲染前 `text.length` 校验 |
| 结构 | `[主题] 事实一句（来源）` + `\n→ 判断。接下来看：观察点。` | 模板占位符 |
| 主题前缀 | `【冲突】/【科技】/【社会运动】`，对应 `TAG_THEMES` 三色（玫红/青蓝/琥珀） | 复用现有 `tagTheme()` |
| 实体/地区 | 不重新发明高亮，沿用 DocumentCard 的实体紫/地区青 | 组件层处理 |
| 概率/推演 | **不出现**。未过门的能力不进脉搏卡 | 文案层禁用 |
| 来源 | 保留括号内媒体名，链接由卡片数据自带（服务端拼，不让模型生成） | 数据层 |

## 模板

**中文**
```
【{主题}】{事实一句话，含关键数字或人名}（{媒体}）
→ {为什么重要，一句判断}。接下来看：{一个可核验的观察点}。
```

**English**
```
[{Theme}] {one factual sentence with key number/name} ({outlet})
→ {why it matters, one line}. Watch for: {one verifiable signal}.
```

## 钩子三律（审稿清单）

1. **判断 ≠ 复述**：钩子第一句必须说出「这意味着什么」，不是换个说法重复事实。
2. **观察点可核验**：「接下来看」必须指向一个具体、可查的事件/数据/声明，不写空话（「值得关注」「让我们拭目以待」禁用）。
3. **诚实边界**：不预测概率、不下立场性结论；平台不做背书（README 合规段口径）。

## 样例（素材：brief-19，2026-10-08 ~ 10-15 周报，全部实测 ≤280 字符）

### 样例 1 · 冲突 · 泽连斯基/停火（zh 75 / en 217 字符）

> 【冲突】泽连斯基：俄方未理会特朗普停火呼吁，基辅遭袭前无预警（卫报）
> → 停火调停连续落空，说明谈判筹码还没摆上桌。接下来看：俄方是否回应新一轮斡旋。

> [Conflict] Zelensky: Russia ignored Trump's ceasefire call; Kyiv hit with no warning (Guardian)
> → Mediation keeps failing — the bargaining chips aren't on the table yet. Watch for: Moscow's response to the next round.

### 样例 2 · 冲突 · 北溪案开庭（zh 78 / en 212 字符）

> 【冲突】德国开庭审理乌克兰籍男子，被控参与炸毁「北溪」管道（BBC）
> → 两年悬案的第一个法庭现场。接下来看：检方能否把「个人行为」与「国家授意」切割清楚。

> [Conflict] Germany tries a Ukrainian man over the Nord Stream pipeline blasts (BBC)
> → First day in court for a two-year mystery. Watch for: whether prosecutors can separate individual action from state direction.

### 样例 3 · 公共卫生 · 刚果（金）埃博拉（zh 89 / en 198 字符）

> 【公共卫生】刚果（金）埃博拉疫情累计确诊 9066 例、死亡 4381 例，疫苗临床试验进入最后筹备（中新社）
> → 死亡率近半，但这次有本土试验。接下来看：首批接种数据何时公布。

> [Public health] DRC Ebola outbreak: 9,066 cases, 4,381 deaths; vaccine trial in final prep (CNS)
> → Near 50% case fatality — but this time a local trial is coming. Watch for: first inoculation data.

### 样例 4 · 冲突 · 卡比拉与 M23（zh 79 / en 194 字符）

> 【冲突】刚果（金）前总统卡比拉出任含 M23 的反叛联盟领导人（法国24台）
> → 前国家元首站到叛军一边，反对派格局可能重写。接下来看：金沙萨政府的第一反应。

> [Conflict] DRC ex-president Kabila named leader of rebel alliance incl. M23 (France 24)
> → A former head of state joining rebels could redraw the opposition map. Watch for: Kinshasa's first move.

## 反例（为什么这不是「短摘要」）

> ❌ 短摘要版：泽连斯基称俄罗斯未理会特朗普的停火呼吁，基辅遭袭前无预警。
> （只是把段落压短，没有判断、没有观察点，读者看完就走。）

> ✅ 脉搏卡版 = 事实 + 判断 + 观察点（见样例 1）。

## 落地接线（已定稿口径，2026-10-17 Chief 拍板）
**数据源与钩子生成**：
- 钩子落在 **`BriefContent` 结构化 JSON** 的新增 `pulse_hooks` 字段，与 `item_facets` 同模式：**简报生成的同一次 LLM 调用**里，让模型为每条素材输出「一句话事实 + 钩子（为什么重要 + 接下来看）」，只从素材原文提炼，**无则留空**。
- **服务端渲染，前端零模型调用**；老简报没有该字段时回退为不显示钩子（不报错、不占位）。
- 需改动：`brief_daily.md` / `brief_weekly.md` prompt + `BriefContent` schema + `briefs.py` 渲染。

**定位**：tweet 短讯是「**简报级**」可消费形式（周报 bullets → 带钩子的脉搏卡），不是逐文档的 Feed 流——数据量 29 篇/天，简报级策展过的 top 故事才撑得起「短讯」。

**组件参考**：
- 字数守卫：渲染前校验 `length ≤ 280`，超长截断到观察点前的句号并附 `…`（宁缺毋滥）。
- 主题前缀颜色直接复用 `tagTheme()`；实体/地区高亮复用 `highlightKeywords()`。
- 脉搏卡文本源：`GET /briefs/latest?kind=daily|weekly` 的 `sections[].bullets_zh/en` + `pulses`；来源链接由服务端拼，前端不生成。

## brief-21 验收结论（写手 · 2026-10-18）

**钩子三律：6/6 全过。** 每条钩子都有独立判断（不是复述事实）、可核验观察点（官方表态/独立核实/市场反应/来源归属）、零概率零推演。「停火期间持续平民伤亡，凸显局势脆弱」「若获官方确认将改变力量格局」这类措辞都守住了「从素材可推导」的边界。来源名齐、双语结构齐。

**但预算记账有一个漏洞要修：渲染全文本 6/6 超预算。**

实测（brief-21，EN 全部超）：

| 记账层 | pulse 1 EN | 判定 |
|---|---|---|
| fact+hook（validator 记账） | 275 | ✅ ≤280 通过 |
| + `[conflict] ` 前缀（11）+ `\n→ `（3） | 289 | ❌ 渲染超长 |

六条 EN 全部 286–290。`_fit_budget` 只对 `fact+hook` 记账，没算前端渲染时的 **section 前缀（`[conflict] ` / `【冲突】`）** 和 **`\n→ ` 接续符**——这是「单字段合规、合计超长」的第三个变体（字段超长 → 合计超长 → 现在：合计合规、渲染超长）。

**修法（一句话）**：`PULSE_TEXT_BUDGET` 的记账基数改为「渲染全文本」= 前缀 + fact + `\n→ ` + hook，即 `_fit_budget` 的预算检查里扣掉前缀与接续符的固定开销（zh 前缀按 SECTION_LABELS 实际文案长度计，en 前缀 `[conflict] ` 11 + 接续 3 = 14 固定开销）。修正后 fact/hook 的可用空间各缩 14 字符左右，钩子下限 60 不受影响。

在修好之前，前端 `PulseList` 按现库渲染出的 EN 卡就是 286–290 字符——**契约是 ≤280，现在这批是不合规的**，别以「反正差不多」放行。

—— 写手 · 2026-10-17
