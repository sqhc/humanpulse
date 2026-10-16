# handoff：humanpulse —— 交接给新团队

> 生成时间：2026-10-13（America/New_York）
> **更新：2026-10-14**——团队已完成 P0–P3，P4 已被数据判定为不可行（见 §0 与 §4）
> 交接时 HEAD：`6b10497`，分支 `main`，工作树**干净**（0 个未提交文件）
> 仓库：https://github.com/sqhc/humanpulse （private）

本文只写**接手前必须知道的事**。已沉淀到别处的细节一律给路径，不在这里复述。

## 0. 最新进展（2026-10-14）

**P0–P3 已完成并推送**（`3ad8b4f`→`6b10497`）：卡片网格接进 storyboard、双语成片
（英文语速实测 19.0 字/秒）、管理台模型建议列、推演→预测登记接线 + 判官常驻。

**P4 领域微调：已判定不可行，不要再排期。** 原判断是「样本不够、要等时间」。
两个决定性实验推翻了它（`make tune-judgement`，7 天 horizon，锁定测试集 n=145）：

| | coverage 措辞 | progress 措辞 |
| --- | --- | --- |
| 原始 Brier 技能分 | -1.167 | -0.825 |
| 原始 **AUC** | 0.601 | **0.574** |
| Platt 后技能分 | -0.012 | -0.005 |
| Platt 后 ECE | 0.067 | 0.027 |
| **Platt 拟合斜率** | **-0.026** | **-0.004** |

三件事要理解：

1. **换措辞救不了**，两种问法都失败。
2. **Platt 的「改善」是假的**：斜率是**负的**，校准器直接把概率压成常数（基率 0.779），
   于是 Brier 回到基线、skill 趋近 0、ECE 看起来很漂亮——但模型信息已被全部丢弃。
   单看 `skill=-0.005` 极易误读成「只差一点就过门」。
3. **这解释了为什么等样本没用**：AUC 0.574 只比随机（0.5）高一点，
   排序能力最多是弱的；攒更多样本只会把置信区间收窄，不会把 0.574 变成 0.7。

为此已把 `metrics.roc_auc` 加为**强制伴随指标**（`6b10497`），
AUC<0.55 时报告会明确写「没有区分能力，攒样本/重拟合都不会改善，
只能换判官或换问题口径」——把「不可用」和「接近可用」在报告层面分开。

**要继续推演，只有两条路**（都需要人决策，不是自动化能解决的）：
- 换云端 Jev（key 有效期内**推荐**，用户 2026-10-15 拍板；概率侧已实测仍未过门，
  AUC 0.528≈随机——「换更强判官」这条路已封，见
  [ADR-0015](docs/adr/0015-judgement-and-projection.md)「云端 Jev 复测」节；key 10-22 到期）；
- 重新设计一个**更机械、更可预测**的客观标签口径，例如
  「事件是否在 N 天内被 ≥M 个**新增**来源报道」——现在的口径（是否还有新报道）
  在基率 0.78 上近乎必然发生，本身就没什么可预测的。

**其它仍然有效**：判官做**分类**可用。按 provider：云端 Jev 原始量表即可用
（AUC 1.000 / F1 1.000，精确率 1.0）；本地 Laya **需校准阈值**（0.406）也可用
（AUC 0.799 全量 / 0.796 锁定测试集，F1 0.882）——「Laya 0.226 不可用」已作废：那是「名义阈值 1.5 +
把入库标题塞进 prompt（context 污染）」双重评估口径问题的产物，不是模型能力，
见 ADR-0015 修订节。生产的实体别名裁决正在用（key 有效期内走 Jev）。
生产用分类、实验用概率——这条边界不要打破。

### 一句话现状

Phase 0–2 完成，Phase 3 基本完成，Phase 4（推演）**做了一半、且被自己的评估门拦住**。
平台已经能跑：33 个已登记源（27 个启用）采集 → DeepSeek 双语分析 → local 语义向量聚类 → 实体时间线
→ 日报/周报 → 带配音与字幕的 MP4。**唯一没打通的是「推演未来影响」**，
而这是项目本来的差异点。

## 1. 核心结论：先读这三条，否则会重复我们踩过的坑

### 1.1 判官模型的概率**不可直接发布**

实测（`make eval-judgement`，247 样本，锁定测试集）：Brier 技能分 **-1.69**、ECE **0.36**
（门槛 skill>0.05、ECE<0.15）。Platt 校准把 ECE 修到 0.07，但拟合斜率只有 **0.0199**——
校准器几乎完全忽略模型输入，只预测基率；技能分仍为负。

**所以 `projection_enabled=false` 是刻意的，不要为了出效果打开它。**
未过门时推演输出会强制标注「未经校准」，这是代码里写死的（`app/briefs/projection.py`）。

### 1.2 但同一个模型做**分类**是可用的

在**人工别名表**（31 组、274 对、人工逐条核对）上测实体对齐：
锁定测试集 **AUC 0.796 / F1 0.882**（校准集选阈值 0.406，测试集报告；
全量口径为 AUC 0.799——两数都对，是两种口径，见 ADR-0015）。
已用于生产的实体别名裁决，实测人工正例自动合并率 97.7%、**误合并 0**。

→ **分工原则：让判官做排序/分类，不要让它给可直接发布的概率。**

### 1.3 簇不能用于纵向评估

实测 702 个簇的跨度**中位数 0 天**（最大 2 天）——因为聚类是按 24 小时窗口合并
「同期报道」的（dedup 语义），天然跨不过时间。
**推演的时间单元必须是实体/话题，不是簇。**

详细论证见 [ADR-0015](docs/adr/0015-judgement-and-projection.md)——**接手请先读这一篇**。

## 2. 已完成（不要重做）

| 能力 | 入口 | 文档 |
| --- | --- | --- |
| 采集源（33 个已登记 / 27 个启用，含中文） | `make collect-once` | [data-sources.md](docs/data-sources.md)、ADR-0002 |
| DeepSeek 双语分析（严格 JSON + 计费） | worker 自动 | ADR-0003 |
| local 语义向量（多语种，384 维） | `make reembed` | ADR-0012 |
| SimHash 去重 + 向量聚类 | pipeline 自动 | ADR-0003 |
| 实体与时间线 | `make entities` / `#/entities` | ADR-0007 |
| 人工别名表（31 组）+ 应用 | `make aliases` | ADR-0009 |
| 日报 / 周报 | `make brief KIND=weekly` | ADR-0006 |
| **判官层**（Jev/Laya，三类原语） | `app/judgement/` | ADR-0015 |
| **推演链路**（3 跳，条件化） | `app/briefs/projection.py` | ADR-0015 |
| **预测登记 + 到期核对** | worker `resolve-predictions`、`GET /predictions/calibration` | ADR-0015 |
| **实体别名裁决**（判官做分类） | `make alias-adjudicate` | ADR-0015 |
| 视频：脚本/字幕/配音/视觉/MP4 | `make video BRIEF_ID=3 RENDER=1 VOICE=1` | ADR-0010/0013/0014 |
| 浅色编辑风版式 + 章节 tab | `VIDEO_THEME=light`（默认） | ADR-0014 |
| 语义搜索 | `#/search`、`GET /search` | ADR-0012 |
| PWA | `#/` 可安装 | ADR-0011 |
| 实时 SSE | `GET /api/v1/stream` | ADR-0008 |
| 管理台 | `#/admin` | — |

**测试基线：后端 242 + 前端 39 = 281 全绿**（`make verify`，2026-10-14 实测）。
上传前必须全绿，见 ADR-0005。

## 3. 判官/推演子系统的使用方式

```bash
make laya-model        # 下载 Laya multilingual 权重（约 660MB）→ .cache/laya/models
make laya-serve        # 起本地判官服务（Jev 兼容路由 127.0.0.1:8077）

make eval-judgement    # 概率质量门禁（未过门以非零码退出）
make tune-judgement    # 措辞对照 + Platt 校准（校准集拟合，锁定测试集报告）
make eval-alignment    # 实体对齐评估（金标准＝人工别名表）
make alias-adjudicate  # 用判官裁决别名候选
```

关键文件：
- `backend/app/judgement/` — `base.py`（三类原语契约）/ `typesafe.py`（Jev+Laya 共用，只差 `base_url`）/ `fake.py`（确定性假实现，CI 用）
- `backend/app/briefs/projection.py` — 链路构造（hop1 扇出 → 按结论分支 hop2 → hop3）
- `backend/app/predictions/` — 登记 / 到期核对 / 校准汇总
- `backend/app/eval/` — `metrics.py`（评分函数）、`judgement.py`（门禁）、`calibration.py`（Platt）、`alignment.py`（分类评估）
- `backend/app/pipeline/alias_adjudication.py` — 两段式别名裁决
- `backend/scripts/laya_serve.py` — 起第十章 `serve.py` 的 launcher（见 §5 陷阱）

### 生产用途与实验用途要分清

- **已可放心用**：实体别名裁决（分类，有实测支撑）。
- **实验性**：`projection_enabled` 相关的一切（概率未验证）。

## 4. 待办（2026-10-14 更新；P0–P3 已完成）

> P0–P3 都已合并推送。保留描述是为了让接手者知道**当时为什么这么做**、
> 以及留下了什么限制。**不要重做。**

### ✅ P0：视频卡片网格（`50ff79c`）

新增 `deep_dive` 分镜 + `_deep_dive_cards()`（`app/video/storyboard.py`），
用确定性信息槽填充（事件/来源/要点/话题/涉及方/地区，空槽省略、最多 6 张）。

**遗留**：这是**占位实现**。用户原意的 6 张语义 facet 卡
（官方回应/研究判断/技术手法/媒体披露/监管合作/第三方观点）需要
「深度调查 agent」产出；当前用确定性槽位代替。
若要落地，改动点在 `_deep_dive_cards()`——**注意别让它调用模型**：
视频链路的设计约束是「文案全部来自已入库简报、零模型调用、可复现」（见 §7）。

### ✅ P1：双语成片（`aa38bc2`）

`--lang both` 已支持；**英文语速已从估的 14.0 实测校准为 19.0**
（`CHARS_PER_SECOND['en']`）。
**遗留**：生产 Linux 没有 macOS `say`，需 `TTS_PROVIDER=command` 模板接 piper。

### ✅ P2：管理台模型建议列（`acfd627`）

实体候选已加「模型建议 + 分数」列。**遗留**：一键采纳尚未做。

### ✅ P3：预测登记接线 + 判官常驻（`3ad8b4f`、`7b3dad3`）

已接上「推演→登记预测」断线、修了 3 个 Docker 环境缺口
（ml 依赖 / typesafe-sdk / host 网络），端到端实测 12 素材 → 21 条预测。

**现状**：27 条预测（21 open / 6 hit），**0 条到期**（horizon 14 天），
所以校准汇总目前没有统计意义。保持判官常驻才会持续积累。

### ❌ P4：领域微调 Laya —— **已判定不可行，不要排期**

见 §0。结论已从「样本不够」升级为「当前问题口径下不可测」。
**继续等待不会改变结论。** 要推进只能换判官或换标签口径——
两者都是人的决策，不是「再跑一会儿就出来了」的任务。

### 明确暂不做

- 打开 `projection_enabled`（未过门：2026-10-15 云端 Jev 复测 skill −0.362 / ECE 0.193 / AUC 0.528≈随机，
  「换更强判官」已被排除，瓶颈在问题口径而非模型强度，见 ADR-0015「云端 Jev 复测」节）
- 抓取原文配图（违反 ADR-0002/0014，视频背景是程序化生成的）
- 云 Jev 用于概率：**已试**（分类近乎完美 AUC 1.000 / 概率不可用）。**key 有效期内（至 2026-10-22）推荐配置
  = 云端 Jev**（用户拍板，`.env.example` 注释已写；仓库/CI 生效默认仍 none）。到期回退 Laya 后别名裁决
  **仍可用但变弱**（AUC 0.799 全量 / 0.796 锁定测试集，F1 0.882，需校准阈值 0.406——「0.226 不可用」已作废，
是双重评估口径问题的产物，不是断崖，见 ADR-0015 修订节）
- X/Twitter 抓取（付费墙 + 违反数据政策）

## 5. 环境陷阱（照抄，别自己摸索）

1. **Node 必须前置 v24**：默认是 v20，vitest 5 会报 `markAsUncloneable is not a function` 且所有测试显示 no tests。
   `export PATH="/Users/shenqing/.nvm/versions/node/v24.21.0/bin:$PATH"`（前置，追加无效）
2. **`uv --extra` 是「只保留」不是「累加」**：只写 `--extra ml` 会卸掉 Pillow，
   渲染时报 `ImportError: cannot import name Image`。Makefile 已固定列全（`ml`+`video`+`judgement`）。
3. **沙箱下缓存目录不可写**：uv / buildx / HF / modelscope / uv tool 都往 `$HOME` 写。
   Makefile 已全部重定向到仓库 `.cache/`；手工命令要自己 export。
4. **`10_本地模型` 不是合法包名**（数字开头 + 中文），直接 `python serve.py` 会报
   `attempted relative import with no known parent package`。用 `scripts/laya_serve.py`（它造合成包）。
5. **Laya 权重约 660MB，已 gitignore**（`.cache/laya/`）；`make laya-model` 可重新下载。
   **不要把权重提交进仓库。**
6. **Docker Desktop 会自动退出**：跑 compose 前先 `docker info`，必要时 `open -a Docker`（启动可能要 1–2 分钟）。
7. **本机 ffmpeg 8.1 没有 drawtext/subtitles**（未编译 libfreetype）：分镜用 PIL 画，
   ffmpeg 只负责编码。**不要改回 drawtext**。
8. **dev API 是 `uvicorn --reload`**：改后端文件会重启并打断在途请求。
   worker 没有 reload，改代码后 `docker compose up -d --force-recreate worker`。
9. **`make smoke` 用独立 project + `scripts/smoke.compose.yml`** 把提供方钉成 `fake`/`hash`，
   不继承开发者 `.env`（否则 `.env` 切到 local 时冒烟会 500）。
10. **必须用 nvm 的 node 跑前端，不能用 DSH 自带运行时里的那个 node。**
    DSH 运行时的 node（`~/.dsh/dsh-runtimes/.../node/bin/node`）与 rolldown 的
    darwin-arm64 原生绑定**代码签名 Team ID 不一致**，`dlopen` 直接失败，
    报错是具有误导性的 `Cannot find native binding ... @rolldown/binding-wasm32-wasi`
    （看起来像缺可选依赖，实际是签名冲突；`pnpm install` 反复重装、删 node_modules 都没用）。
    正确做法就一条 `export`——nvm 的 bin 目录里已经有配套的 pnpm，
    **不需要**再装 pnpm 或做 shim：

    ```bash
    export PATH="/Users/shenqing/.nvm/versions/node/v24.21.0/bin:$PATH"
    node --version   # 必须是 v24.21.0
    pnpm --version   # 必须是 12.3.4（与 package.json 的 packageManager 一致）
    ```

    实测：只加这一行，`pnpm run lint` / `typecheck` / `test` 三项全部通过。
11. **`pnpm install` 会顺手改 `pnpm-lock.yaml`**（自动补一个 `'@pnpm/exe'` 条目）。
    提交前 `git checkout -- pnpm-lock.yaml`，不要把这个噪音带进提交。
12. **长命令要放后台跑，否则会撞工具超时并拿到上一次的陈旧输出。**
    判官评估（几百次模型调用）尤其明显：用 `run_in_background` + 写文件，
    再 `cat` 结果文件，不要在前台等。

### 本机当前状态（接手时已具备，无需重装）

- `EMBEDDING_PROVIDER=local`（已实测生效），`DEEPSEEK_API_KEY` / `ADMIN_API_KEY` 已配置
- `JUDGEMENT_PROVIDER=none`（判官默认关闭），`TTS_PROVIDER=none`
- Laya 权重已在 `.cache/laya/models/multilingual/`（647MB）
- `.cache/video/brief-3-zh.mp4` 已有成片（112MB 缓存目录）
- Postgres 在 `docker compose` 的 **`db`** 服务（不是 `postgres`）

## 6. 复现真实链路（最快上手路径）

```bash
cd "/Users/shenqing/Desktop/Deepseek Harness/humanpulse"
export PATH="/Users/shenqing/.nvm/versions/node/v24.21.0/bin:$PATH"
export UV_CACHE_DIR="$PWD/.cache/uv"

make doctor          # 先体检：依赖、.env、端口
make bootstrap       # 装依赖 + 生成 .env（已存在则跳过）
make ml judging      # 装向量与视频依赖 + 判官依赖
make dev             # 起 db + api + worker
make seed            # 导入源清单（33 个）
export PATH=... && make dev-web   # 前端 #/

# 判官（可选，不跑也不影响其它功能）
make laya-serve &    # 另开一个后台作业；等 /healthz 返回 ok
make eval-alignment  # 用人工别名表验证分类能力

# 出片
make video BRIEF_ID=3 RENDER=1 VOICE=1
```

## 7. 质量约束（不要退化）

- 采集只走公开渠道，被 Cloudflare 拦下就停用而不是绕过（ADR-0002）；
- **不复用第三方图片**：视频背景程序化生成（ADR-0014）；配图须走授权图库；
- 上传前 `make verify` 全绿；接口改动后 `make openapi && pnpm run api-client:generate`；
- 与三个议题（冲突 / 科技 / 社会运动）无关的内容评 0 分不入 Feed；
- **来源清单由服务端按素材拼，不让模型生成链接**；
- 视频脚本/字幕/视觉都来自已入库简报，不额外调用模型（零成本、可复现）；
- **诚实性硬约束**：未通过评估门的能力必须标注「未经校准」，
  预测的「无证据」与「未发生」必须区分（`unresolved` vs `missed`），
  校准汇总只统计已判定的样本。

## 8. 给新团队的工作建议

1. **先读 [ADR-0015](docs/adr/0015-judgement-and-projection.md)** —— 它解释了为什么推演被拦住，
   以及为什么「同一个模型分类可用、概率不可用」。这是本项目最反直觉、也最重要的一条。
2. **先跑 `make verify` 建立基线**，确认真的是 281 项全绿再动手。
3. **不要重做 P0–P3**（已完成），也**不要排期 P4**（已被数据否决，见 §0）。
   真正值得做的下一步是：卡片网格的语义 facet 填充、一键采纳、生产 TTS 接 piper
   （均为 §4 里标注的「遗留」项）。
4. 涉及判官的任何结论，**必须同时报基线、Brier skill 和 AUC**——
   只看三者中的任何一个都会得出错误结论：
   - 准确率会在高基率上骗人（7 天基率 0.78 时，「全猜会发生」就有 0.78）；
   - ECE 会被退化校准骗（把概率压成常数能让 ECE 很好看，模型信息却全丢了）；
   - **skill 接近 0 也不代表接近过门**（本次就是这个陷阱，见 §0）。
5. **诚实的负面结论比虚假的进度有价值。** P4 现在是一个「已被数据关闭的方向」——
   这比让它无限期挂在待办里、每次汇报都说「还在攒样本」要诚实得多。

## 9. 建议下一个会话加载的技能

- `handoff`：再次压缩上下文交接
- `diagnose`：本地绿而 CI 红、或采集/聚类/搜索异常时
- `to-issues` / `to-prd`：把 §4 的 P0–P4 拆成可独立领取的任务
- `archify`：系统已有 6 条流水线（采集/处理/简报/实体/判官/视频），值得画一张图
