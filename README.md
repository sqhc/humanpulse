# humanpulse

> 一个观察人类冲突、科学技术发展与全球社会运动的追踪平台：多源采集 → 去重 → AI 双语摘要与评分 → 聚类 → 日报/周报 → Web 阅读。

当前状态：**Phase 0（骨架）**。后端提供健康检查与配置骨架，前端提供可运行的阅读外壳，采集/摘要流水线自 Phase 1 起接入。

- 数据源政策：[docs/adr/0002-data-source-policy.md](docs/adr/0002-data-source-policy.md)
- 架构决策：[docs/adr/](docs/adr/)
- 运维手册：[docs/runbook.md](docs/runbook.md)
- 贡献与上传规则：[docs/contributing.md](docs/contributing.md)

## 架构

```
采集层           处理层                        服务/展示层
RSS/GDELT/       normalize → SimHash 去重 →     FastAPI (/api/v1)
ReliefWeb/       DeepSeek 双语摘要+评分+标签 →   ├─ Web (React + Vite)
手动上传         向量去重/聚类 → 日报/周报        └─ 后续：Tauri 桌面 / Expo 移动
```

- 后端是唯一数据源；所有客户端复用同一份 REST 契约与 `packages/api-client` 生成的类型。
- 存储：PostgreSQL + pgvector（文章、向量、简报同库）。
- 部署：单台 VPS + docker compose + Caddy（[ADR-0004](docs/adr/0004-deployment.md)）。

## 快速开始

```bash
make doctor        # 检查本机依赖
make bootstrap     # 安装依赖并生成 .env（需填入 DEEPSEEK_API_KEY / ADMIN_API_KEY）
make dev           # 起 db + api + worker（docker compose）
make dev-web       # 另开终端：起前端 http://localhost:5173
open http://localhost:8000/api/v1/health
```

不用 Docker 也可以只跑后端：

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload
```

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `make doctor` | 检查 uv / pnpm / node / docker / .env / 端口 |
| `make bootstrap` | 安装依赖并准备 `.env` |
| `make dev` / `make dev-web` | 起后端依赖服务 / 前端开发服务器 |
| `make smoke` | 整套起栈 → 探活 `/api/v1/health` → 收栈 |
| `make lint` / `typecheck` / `test` | 分别运行检查 |
| `make verify` | **上传前必须全绿**：lint + typecheck + test + build + compose 校验 |
| `make openapi` | 导出 `backend/openapi.json`（供 api-client 生成类型） |
| `make migrate` | 执行 Alembic 迁移 |

## 目录结构

```
backend/           FastAPI + SQLAlchemy + Alembic + 采集器 + 流水线
web/               React 19 + Vite + Tailwind v4 + TanStack Query
packages/api-client/     共享 TS API 客户端（类型由 OpenAPI 生成）
packages/design-tokens/  共享设计变量
infra/seed/        初始数据源清单
docs/              ADR、数据源政策、runbook
scripts/           doctor / smoke / deploy / restore-drill
```

## 数据与合规

- 只采集公开内容；遵守 robots.txt、站点 ToS 与各 API 配额；每条记录保留来源链接与抓取时间。
- 默认只存元数据 + 短引用 + 摘要，**不对外提供全文**（`STORE_FULLTEXT=false`）。
- 提交删除申请：`POST /api/v1/takedown`；涉及个人的实体记录提供删除路径。
- **不使用** X（Twitter）抓取、**不绕过** Cloudflare 等防护；X 官方付费 API 不在路线图内。
- AI 生成内容一律标注，平台不做立场性结论。

## 免责声明

本项目是信息聚合与观察工具，聚合内容来自第三方公开来源，版权归原作者所有；摘要由大模型生成，可能存在错误，请以原文为准。平台不构成任何形式的立场表达或事实背书。

## 路线图

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Phase 0 | 骨架、CI、compose、ADR、GitHub 仓库 | 进行中 |
| Phase 1 | 数据模型、RSS/GDELT/手动上传、SimHash + DeepSeek 摘要 + 向量去重、Feed/详情 | 待开始 |
| Phase 2 | 日报/周报、管理台、Reddit/Bluesky/Mastodon/ReliefWeb、SSE、VPS 上线 | 待开始 |
| Phase 3 | 视频简报、移动端、实体时间线、语义搜索、深度调查 agent | 待开始 |
