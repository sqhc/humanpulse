# P1+P2 创意方向：前端 React 组件设计稿

**Chief 纠正**：P1/P2 是 `web/src/` 里的 React 组件，不是 README 里的静态 archify 图。README 架构图已完成（`d4af62a`/`9c9dce0`），再产生 PNG 是重复劳动。

纠正的 3 处事实错误（重写时已修正）：
1. **判官门禁数据**：Laya old baseline (n=60) Brier −1.69/ECE 0.36 已过时。改为 Jev 复测：skill −0.362 / ECE 0.193 / **AUC 0.528**（未过门）
2. **表/文档存在性**：`entity_mentions` 表、ADR-0007 均已确认存在（见 grep 结果）
3. **配色方案**：P2 的 "Jev=红/Laya=橙" 编造。改为**复用视频卡片 3×2 语义配色体系**（见下）

---

## 方向概览（Chief 批准）

| 方向 | 交付形式 | 状态 |
|---|---|---|
| **P1** 流水线概览 | `web/src/components/PipelineOverview.tsx`（React 组件） | 待实现 |
| **P2** 实体时间线 | `web/src/components/EntityTimeline.tsx`（React 组件） | 待实现 |
| **P3** 概率可视化 | 暂缓（口径未过门） | - |

---

## P1：流水线概览

### 1. 组件位置
- **放置**：`FeedView` 顶部，或新增 `#/pipeline` 路由
- **导入路径**：`components/PipelineOverview.tsx`
- **依赖**：`documents.status` 流转态、判官边界标识

### 2. 读取的现有接口（无需新增）
| 数据 | 接口 | 说明 |
|---|---|---|
| 文档状态 | `GET /documents`（带 `status` 过滤） | pending→enriched/rejected/deduped/failed |
| 判官边界 | `GET /documents/{id}` | 结构化内容含 `structured.projection` 判断 |
| 简报列表 | `GET /briefs/latest?kind=weekly` | 最新一期 |

**不需要新增后端接口** - 全部复用现有 REST 契约。

### 3. 组件结构

```tsx
interface PipelineOverviewProps {
  /** 简报 ID，可选；未指定则展示最近一期 */
  briefId?: string;
  /** 是否显示判官边界标注 */
  showJudgeGate?: boolean;
}

/** 流水线 5 阶段颜色（复用视频卡片 3×2 语义体系） */
const STAGE_COLORS = {
  fetch: "bg-blue-100 text-blue-800",      // 采集 - 蓝色
  enrich: "bg-amber-100 text-amber-800",   // 富化 - 琥珀色  
  store: "bg-emerald-100 text-emerald-800", // 入库 - 祖母绿
  judge: "bg-rose-100 text-rose-800",      // 判官 - 玫红色（概率未过门标注）
  output: "bg-teal-100 text-teal-800",      // 输出 - 青色
};
```

### 4. 交互设计
- **顶部横条**：5个阶段按钮/圆点，当前激活态高亮
- **中部状态**：
  - 采集：显示 33 源 · ~430 条 计数
  - 富化：显示 "LLM 双语摘要 + 评分 中"
  - 入库：显示 "PostgreSQL + pgvector · 状态流转"
  - **判官**：**关键** - "概率未过门：skill −0.362 / ECE 0.193 / AUC 0.528 · projection_enabled=false · 强制标注「未经校准」"
  - 输出：显示 "简报 · 视频 (SRT → ffmpeg → MP4)"
- **底部卡片**：
  - 循环卡片："33 源 · 单轮约 430 条入库"
  - 判官门禁卡片："概率未过门 · AUC 0.528 · 不可发布"

### 5. 与现有视图的关系
- 与 `#/admin/runs` 独立——只读展示，不涉及作业控制
- 与 `#/entities/{id}` 独立——流水线全貌，非单实体详情
- 语言切换：同步 `README.md` / `README.en.md` 中的 `## Pipeline Flow` 锚点

---

## P2：实体时间线

### 1. 组件位置
- **放置**：`EntityDetailView` `#/entities/{id}` 页面的侧边栏/底部面板
- **触发**：在实体详情页面，展开时间线面板

### 2. 读取的现有接口（无需新增）
| 数据 | 接口 | 说明 |
|---|---|---|
| 实体列表 | `GET /entities` | 按提及/最近排序，可搜索 |
| 实体详情 | `GET /entities/{id}` | 包含 per-day 时间线 |
| 提及计数 | `GET /entities/{id}/mentions` | 每日提及数（可选） |
| 别名表 | `GET /admin/entity-aliases` | 中/China 合并情况 |

**不需要新增后端接口** - 复用现有 `/entities` 契约。

### 3. 组件结构

```tsx
interface EntityTimelineProps {
  /** 实体 ID */
  entityId: string;
  /** 时间范围：7/15/30 天 */
  timeRange?: "7d" | "15d" | "30d";
  /** 展示哪个判官分类 */
  judgeProvider?: "jev" | "laya" | "both";
}
```

### 4. 交互设计
- **搜索框**：输入实体名，筛选 `entities` 表（模糊匹配 `name` 字段）
- **时间范围选择**：最近 7/15/30 天，切换显示不同时间段的提及数
- **分类色切换**：
  - **Jev**：红色语义配色（复用视频卡片体系）
  - **Laya**：橙色语义配色（同一色谱，不同深浅）
  - **Both**：并排展示，悬停高亮对应区间
- **悬停效果**：显示该天的具体提及数量、来源文档、判官分类结果
- **别名合并点击**：跳转 `#/admin/jobs/aliases` 进行合并确认

### 5. 语义配色体系（复用视频卡片 3×2）
```
类别        | Jev 配色     | Laya 配色
------------|-------------|------------
实体提及     | bg-rose-100  | bg-orange-100
同类聚类     | bg-emerald-100| bg-amber-100
别名匹配     | bg-amber-100  | bg-rose-100
```
*注：以上为浅底类名，实际文字色需对应深色（text-rose-800 / text-orange-800）*

### 6. 与现有视图的关系
- 与 `#/entities/{id}` 紧耦合——面板是实体详情的扩展
- 与 AdminView `#/admin/jobs/aliases` 耦合——别名合并后刷新面板显示
- 语言切换：与实体详情页语言保持一致

---

## 实现路线图

### Commit 1：P1 流水线概览 (约 4-5 小时)
**文件变更**：
- `web/src/components/PipelineOverview.tsx` - 新建 React 组件
- `web/src/components/PipelineOverview.css` - 样式（复用视频卡片 3×2 配色）
- `web/src/routes.tsx` - 新增 `#/pipeline` 可选路由（或放在 FeedView 顶部）
- `README.md` - `## Pipeline Flow` 改为指向 React 组件说明（或保持 archify 图并存）
- `README.en.md` - English 版同样

**验收**：
- `make verify` 全绿 → 推送
- Chief 审阅组件输出 → 确认交付

### Commit 2：P2 实体时间线 (约 4-5 小时)
**文件变更**：
- `web/src/components/EntityTimeline.tsx` - 新建 React 组件
- `web/src/components/EntityTimeline.css` - 语义配色样式
- 修改 `web/src/components/EntityDetailView.tsx` - 在侧边栏接入 Pipeline/Timeline 面板
- `README.md` / `README.en.md` - 在 EntityDetailView 下方嵌入时间线说明

**验收**：
- `make verify` 全绿 → 推送

---

## 备注

1. **P3 暂缓**：概率未校准（AUC 0.528 < 门槛），现在上概率雷达等于展示未验证结论。等口径问题解决并过门后再设计。

2. **视觉一致性**：
   - P1/P2 均复用**视频卡片 3×2 语义配色体系**（已在视频简牌中验证）
   - 两组件颜色深浅统一，避免在同一页面出现冲突色
   - 浅底使用 `bg-*-100`，文字使用 `text-*-800` 对应深色

3. **硬约束检查**：
   - ✅ `projection_enabled=false` - 符合 ADR-0015，P1 判官环节标注 "未经校准"
   - ✅ 无新增后端接口 - 复用现有 `/documents`、 `/entities` 契约
   - ✅ `make verify` 全绿 - 每个 commit 都是绿色

4. **与旧设计的区别**：
   - ✅ 之前的 `design-p1p2-collection-timeline.md` 是 **archify 静态图** - **已废弃**
   - ✅ 现在的是 **React 组件** - 可交互、实时展示、放在 `web/src/components/`
   - ✅ Chief 已确认：用户要的是「前端」，不是「README 图」

---
*设计完成于 2026-10-16。下一步：@程序员 按此规范实现 P1 React 组件 PipelineOverview.tsx。*