# ADR-0004：部署形态（单台 VPS + docker compose）

- 状态：已接受
- 日期：2026-01
- 决策者：sqhc

## 背景

个人项目：预算敏感、运维人力有限、需要数据自主。候选方案为托管云（Supabase + Fly/Railway + Vercel）与自托管单机。

## 决策

**生产环境 = 单台 VPS + `docker-compose.prod.yml` + Caddy（自动 TLS）。**

### 拓扑

```
Internet ──> Caddy (80/443, TLS, 安全响应头)
               ├── /api/*  ──> api (FastAPI, 内网 8000)
               ├── /       ──> web (nginx 托管前端构建产物)
               └── (同机)     worker (定时采集/处理/简报)
                             db (pgvector/pgvector:pg17, 数据卷)
```

- 规格起点：2 vCPU / 4 GB / 40 GB SSD；出口带宽决定采集频率上限。
- 防火墙仅开放 22 / 80 / 443；数据库不映射到宿主机端口。
- 所有服务 `restart: unless-stopped`；镜像来自 GHCR（`ghcr.io/sqhc/humanpulse-api`、`-web`），VPS 只 `pull`，不现场构建。

### 发布

1. 打 tag（`v0.1.0`）触发 CI 构建并推送镜像到 GHCR。
2. VPS 上 `make deploy`（或 GitHub Actions 的 deploy job）：`docker compose -f docker-compose.prod.yml pull && up -d`。
3. 回滚 = 用上一个 tag 重新 pull + up。

### 备份与恢复

- 每日 `pg_dump`（保留 14 天）→ 本地目录 + 可选对象存储。
- `make restore-drill` 在临时库上恢复并校验表数量，纳入 runbook。
- 目标：RPO 24h，RTO 1h。

### 为什么不是托管云

Supabase 方案更快，但（a）成本随数据与带宽上涨，（b）数据出境与依赖第三方评估未定义，（c）本项目的向量与全文检索都在同一 Postgres 内，自托管一个容器即可覆盖。待流量或运维压力真正上升，再把 `DATABASE_URL` 指向托管 Postgres 即可迁移——compose 文件结构不变。

## 后果

- 需要自己维护 VPS：升级、证书（Caddy 自动）、磁盘水位、备份校验。runbook 覆盖这些。
- 单点故障：VPS 挂了站点即下线；对个人项目可接受，恢复路径明确（重建 + 恢复备份 + 拉镜像）。
