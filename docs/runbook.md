# 运维手册

覆盖日常巡检、发布、回滚、备份恢复与常见故障。政策与架构背景见 [ADR-0002](adr/0002-data-source-policy.md)、[ADR-0004](adr/0004-deployment.md)。

## 1. 日常巡检（每天 5 分钟）

```bash
curl -s https://<domain>/api/v1/health | python3 -m json.tool
curl -s https://<domain>/api/v1/ready  | python3 -m json.tool   # 期望 database ok
```

再检查：

- `fetch_runs` 最近 24 小时失败率（Phase 1 起有数据）
- `llm_usage` 当日成本是否超预算
- 磁盘水位 `df -h`（Postgres 数据卷 + 备份目录）
- `docker compose -f docker-compose.prod.yml ps` 是否有反复重启的容器

## 2. 首次部署（VPS）

```bash
# 1) 基础环境
apt update && apt install -y docker.io docker-compose-plugin git
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw enable

# 2) 代码与配置
git clone https://github.com/sqhc/humanpulse.git /opt/humanpulse
cd /opt/humanpulse
cp .env.example .env && $EDITOR .env   # 必填：POSTGRES_PASSWORD / ADMIN_API_KEY / DOMAIN / DEEPSEEK_API_KEY

# 3) 登录 GHCR（若镜像为私有包）
echo $GHCR_TOKEN | docker login ghcr.io -u sqhc --password-stdin

# 4) 起栈
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

DNS：把 `DOMAIN` 的 A 记录指向 VPS 公网 IP，Caddy 会自动申请证书（需 80/443 可达）。

执行数据库迁移（每次部署新版本后都要跑）：

```bash
docker compose -f docker-compose.prod.yml exec api python -m app.cli migrate
# 首次导入数据源清单：
cp infra/seed/sources.yaml /tmp/ && docker compose -f docker-compose.prod.yml exec api \
  sh -lc 'python -m app.cli seed --file /tmp/sources.yaml' 2>/dev/null || \
  echo "提示：镜像内没有 infra/，可在宿主机执行 make seed（需能连到数据库）"
```

冒烟自检（不联网、不花钱，用合成数据验证整条流水线）：

```bash
docker compose -f docker-compose.prod.yml exec -T -e LLM_PROVIDER=fake -e EMBEDDING_PROVIDER=hash \
  api python -m app.cli demo
```

## 3. 发布与回滚

发布：

```bash
git tag v0.1.0 && git push origin v0.1.0   # 触发 CI 构建并推送镜像
ssh vps 'cd /opt/humanpulse && TAG=v0.1.0 make deploy'
```

回滚：

```bash
ssh vps 'cd /opt/humanpulse && TAG=v0.0.9 make deploy'
# 若 schema 也需回退（极少见）：
docker compose -f docker-compose.prod.yml exec api python -m app.cli migrate --downgrade -1
```

> 数据库迁移前务必先备份；`downgrade` 不可逆地丢数据。

## 4. 备份与恢复

备份（也可放入 crontab，每天 03:30）：

```bash
cd /opt/humanpulse
mkdir -p /var/backups/humanpulse
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > /var/backups/humanpulse/humanpulse-$(date +%F).dump
find /var/backups/humanpulse -name '*.dump' -mtime +14 -delete
```

恢复演练（在临时库上做，不动生产）：

```bash
make restore-drill DUMP=/var/backups/humanpulse/humanpulse-2026-01-01.dump
```

目标：RPO 24h，RTO 1h。演练每季度至少一次，结果记在本文档末尾。

## 5. 常见故障

| 症状 | 排查 | 处理 |
| --- | --- | --- |
| `/api/v1/ready` 返回 503 | `docker compose logs db`；磁盘是否写满 | 恢复磁盘或重启 db；磁盘满时先扩容再起容器 |
| api 容器反复重启 | `docker compose logs api --tail=100` | 若是 `ADMIN_API_KEY` 默认值导致（生产环境会拒绝启动），在 `.env` 填强随机值 |
| 证书申请失败 | `docker compose logs caddy`；80/443 是否放行；DNS 是否解析 | 修 DNS/防火墙后 `docker compose restart caddy` |
| 采集大量失败 | `fetch_runs` 的 `error` 字段 | 单源连续失败 3 次会自动停用；确认对方改版或封禁后再手动启用 |
| LLM 成本飙升 | `llm_usage` 按天聚合 | 调低 `LLM_DAILY_TOKEN_BUDGET`；检查是否有源在刷重复内容 |
| 前端白屏 | 浏览器控制台；`web` 容器是否 200 | 重新 `pull` 并 `up -d web`；确认构建产物与后端契约一致 |

## 6. 演练记录

| 日期 | 项目 | 结果 | 备注 |
| --- | --- | --- | --- |
| 待填 | 备份恢复 | - | - |
| 待填 | 回滚到上一 tag | - | - |

## 7. 简报（日报 / 周报）

生成：

```bash
make brief                      # 日报，当天已有则跳过
make brief KIND=weekly          # 周报，本周已有则跳过
FORCE=1 make brief KIND=weekly  # 强制重跑（会真实调用 LLM）
```

自动生成：worker 在 `BRIEF_HOUR`（默认 6 点）之后每 15 分钟探一次；周报只在 `BRIEF_WEEKDAY`（默认周日）当天。
生成函数幂等（同一周期已有简报就跳过），所以"探多次"是安全的。

排查：

- 接口：`GET /api/v1/briefs/latest?kind=daily|weekly`；没有简报时返回 404（前端显示空态）。
- 失败时整批抛出，**不会**留下半成品简报；同一天可以重跑。
- 模型输出校验失败会自动重试一次（见 `app/llm/client.py` 的 `_call_with_repair`）；两次都失败才报错。
- 成本：`llm_usage` 里按 model 记录；周报一次调用约 6.5k 输入 / 8.7k 输出 token。

## 8. 管理台

浏览器打开 `#/admin`：填管理员 API Key（只存在本机 localStorage），即可查看数据源状态、
手动触发采集/处理/日报/周报、查看最近采集批次与 LLM 用量。写操作需要 Key，读数据源不需要。