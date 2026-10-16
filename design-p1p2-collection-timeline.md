# P1+P2 创意方向详细设计稿

**基于 Chief 批准的递进方案**：P1（流水线流）是骨架 → P2（实体时间线）是血肉 → P3（概率雷达）留作未来

---

## 概述

本设计实现「收集→推演」的前两个递进方向：

- **P1**: 端到端流水线可视化（采集→处理→简报→判官→视频），标注判官边界与 `projection_enabled=false` 的诚实说明
- **P2**: 在 P1 的判官环节展开实体时间线，用 Jev/Laya 分类颜色区分，复用现有数据

总工时约 6-8 小时，分两个 commit 推送，每个 `make verify` 全绿后推下一个。

---

## P1：端到端流水线流可视化

### 1. 页面位置

**位置**：`## Pipeline Flow` 节点，位于 `## Architecture` 之后、`## Judge models & projection` 之前

在 `README.md` 中的锚点位置：`# humanpulse` → `## 架构` → **`## Pipeline Flow`**（新增）→ `## 判官模型与推演`

同理在 `README.en.md` 中：`## Architecture` → **`## Pipeline Flow`**（新增）→ `## Judge models & projection`

### 2. 数据来源（现有 vs 新增）

| 数据 | 来源 | 状态 |
|---|---|---|
| 源头列表 | `infra/seed/sources.yaml` → DB | ✅ 已有 |
| 文档状态流转 | `documents.status` 字段值: pending→enriched/rejected/deduped/failed | ✅ 已有 |
| 流水线步骤 | SimHash去重 → 语义向量聚类 → 摘要评分 → 日报/周报 Top N | ✅ 已有 |
| 视频流程 | 分镜 → SRT → ffmpeg 程序化视觉 → MP4 | ✅ 已有 |
| 判官边界 | `projection_enabled=false` 硬约束 + `structured.projection is None` | ✅ 已有 |

**不需要新增后端接口** - 所有数据均来自现有模型。

### 3. 组件划分

```
flowchart TD
    A[RSS/GDELT/ReliefWeb] -->|fetch| B[Backend API]
    B -->|enrich (LLM call)| C[DeepSeek LLM]
    C -->|writeback| D[PostgreSQL + pgvector]
    D -->|serve| E[React Frontend]
    D -->|footage| F[Video Renderer]
    C -->|ask| G[Judge: Jev/Laya]
    G -->|classify| D
    
    style A fill:#lightgray,stroke:#333,stroke-width:2px
    style B fill:#b3e5fc,stroke:#333,stroke-width:2px
    style C fill:#fff3e0,stroke:#333,stroke-width:2px
    style D fill:#e8f5e9,stroke:#333,stroke-width:2px
    style E fill:#f3e5f5,stroke:#333,stroke-width:2px
    style F fill:#fff8e1,stroke:#333,stroke-width:2px
    style G fill:#ffebee,stroke:#333,stroke-width:2px
```

### 4. 交互设计

- **顶部**：标题 "人类冲突追踪平台：端到端流水线"，语言切换链接
- **中部**：水平流程图，5个阶段按顺序排列：
  1. **采集** - RSS/GDELT/ReliefWeb 源（带计数：33 源 · ~430 条/轮）
  2. **富化** - DeepSeek 双语摘要 + 评分 + 标签
  3. **入库** - PostgreSQL + pgvector，状态流转 pending→enriched/rejected/deduped/failed
  4. **判官** - Jev/Laya 分类边界，标注 "概率未过门：不发布，强制标注「未经校准」"
  5. **输出** - 简报/周报 · 视频简报 (分镜 → SRT → ffmpeg → MP4)
- **底部**：卡片摘要
  - 循环卡片："33 源 · 单轮约 430 条入库"
  - 判官门禁卡片："概率未过门 · Brier skill −1.69 · ECE 0.36 · projection_enabled=false"

### 5. 与现有视图的关系

- 复用现有 `entities` 表数据（未新增字段）
- 与 AdminView `#/admin/runs` 保持独立——本可视化是只读展示，不涉及交互修改
- 与 EntitiesView `#/entities/{id}` 保持独立——展示的是流水线全貌，非单实体详情

---

## P2：实体时间线扩展

### 1. 页面位置

**位置**：P1 流水线图的**第 4 环节（判官）下方**，作为可选展开面板

在流水线图右侧或下方作为可折叠面板：
- 标题："实体时间线 · Judge adjudication"
- 只有当有实体被标记时才显示

### 2. 数据来源

| 数据 | 来源 | 状态 |
|---|---|---|
| 实体列表 | `entities` 表 | ✅ 已有 |
| 实体提及 | `entity_mentions` 表 | ✅ 已有 |
| 时间线按天 | `ADR-0007` 实体时间线实现 | ✅ 已有 |
| 判官分类 | `Jev` (AUC 1.000) / `Laya` (AUC 0.799) | ✅ 已有 |
| 别名表 | `entity_aliases.yaml` (中/China 合并) | ✅ 已有 |

**不需要新增后端接口** - 复用现有 `entities`、`entity_mentions`、`entity_aliases`。

### 3. 组件划分

#### 实体时间线图

```
实体: "中国政府工作报告" (China + 中国 merged)
时间轴: 最近 30 天
颜色: Jev=红/Laya=橙 (分类结果)
数据点: 每天的提及计数
```

#### 分类图例

- **红色**: Jev 分类 - 高置信度
- **橙色**: Laya 回退 - 中置信度  
- **灰色**: 待分类 - 概率未过门

### 4. 交互设计

- **搜索框**: 输入实体名，筛选 `entities` 表
- **时间范围选择**: 最近 7/15/30 天
- **颜色切换**: 展示 Jev 还是 Laya 分类颜色
- **悬停**: 显示该天的具体提及数量和来源
- **别名合并点击**: 跳转到 `#/admin/jobs/aliases` 进行合并确认

### 5. 与现有视图的关系

- **与 AdminView 耦合**：勾选实体别名合并后，刷新本可视化显示新的合并结果
- **与 EntitiesView 独立**：本面板是时间线汇总，EntitiesView 是单实体详情页
- **数据流向**：Entities表的变更 → 别名表确认 → 本面板实时刷新

---

## 实现路线图

### Commit 1：P1 实现 (约 3 小时，make verify 全绿)

**文件变更**：
- `README.md`: 新增 `## Pipeline Flow` 节点 + 流水线图 Markdown
- `README.en.md`: 新增 `## Pipeline Flow` 节点 + English 流水线图
- `architectures/pipeline-showcase.html`: 新建 archify spec + export
- `architectures/pipeline-showcase.png`: 生成 PNG export
- `architectures/pipeline-showcase.svg`: 生成 SVG (双主题)

**验收**：`make verify` 全绿 → 推送

### Commit 2：P2 实现 (约 3-5 小时，make verify 全绿)

**文件变更**：
- `README.md`: 在 P1 流水线图下方新增可折叠实体时间线板块
- `README.en.md`: English 版同样新增
- `architectures/entity-timeline-showcase.html`: 新建实体时间线 archify spec + export
- `architectures/entity-timeline-showcase.png`: PNG export
- 可选：`scripts/` 下的可视化生成脚本

**验收**：`make verify` 全绿 → 推送

---

## 备注

1. **P3 (概率雷达) 暂缓**：概率未校准（Brier −1.69，ECE 0.36，ADR-0015 硬约束），现在上雷达等于展示未验证结论。等口径问题解决并过门后再设计。

2. **视觉一致性**：
   - P1 使用 archify 正规 export（无工具栏、完整不裁切、双主题 SVG）
   - P2 与 P1 视觉风格统一，同一色系（青色流水线 + 绿色实体时间线）
   - 两图在 README 中中英对齐，锚点 1:1 对齐

3. **硬约束检查**：
   - ✅ `projection_enabled=false` 未开 - 符合 ADR-0015
   - ✅ 概率未过门 - 标注 "未经校准"
   - ✅ 无第三方图片复用 - 程序化生成
   - ✅ `make verify` 全绿 - 每个 commit 都跑

4. **交付后**：
   - 写手将两图嵌入双版 README `## Pipeline Flow` 节点
   - Chief 审阅后决定是否启动 P3
   - 如有界面改动，记得 `make openapi` + `pnpm run api-client:generate`

---
*设计完成于 2026-10-16。下一步：@程序员 根据设计实现 P1。*