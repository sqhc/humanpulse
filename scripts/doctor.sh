#!/usr/bin/env bash
# 检查本机依赖、.env 与端口占用。docker daemon 未启动只警告，不阻断。
set -uo pipefail

cd "$(dirname "$0")/.."

fail=0
warn=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail + 1)); }
note() { printf '  \033[33m!\033[0m %s\n' "$1"; warn=$((warn + 1)); }

need_cmd() {
  if command -v "$1" >/dev/null 2>&1; then ok "$1 ($("$1" --version 2>&1 | head -1))"
  else bad "缺少 $1 —— $2"; fi
}

echo "== 工具链 =="
need_cmd uv "安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
need_cmd pnpm "安装: corepack enable"
need_cmd node "安装 Node.js >= 22.12"
need_cmd python3 "安装 Python >= 3.12"
need_cmd docker "安装 Docker Engine 或 Docker Desktop"
need_cmd git "安装 git"

if command -v node >/dev/null 2>&1; then
  node_major=$(node -p 'process.versions.node.split(".")[0]')
  node_minor=$(node -p 'process.versions.node.split(".")[1]')
  if [ "$node_major" -gt 22 ] || { [ "$node_major" -eq 22 ] && [ "$node_minor" -ge 12 ]; }; then
    ok "Node 版本满足 Vite 8 要求"
  else
    bad "Node $node_major.$node_minor 过低：前端测试/构建需要 >= 22.12（本项目实测用 nvm 的 v24）—— export PATH=\"/Users/shenqing/.nvm/versions/node/v24.21.0/bin:\$PATH\""
  fi
fi

echo "== Docker =="
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    ok "docker daemon 可用 ($(docker info --format '{{.ServerVersion}}'))"
  else
    note "docker daemon 未运行 —— make dev / make smoke 需要先启动 Docker Desktop"
  fi
  if docker compose version >/dev/null 2>&1; then ok "docker compose ($(docker compose version --short 2>/dev/null))"
  else bad "缺少 docker compose 插件"; fi
fi

echo "== 环境文件 =="
if [ -f .env ]; then ok ".env 已存在"; else note ".env 不存在，make bootstrap 会从 .env.example 生成"; fi

echo "== 判官（JUDGEMENT_PROVIDER）=="
env_val() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | xargs; }
if [ ! -f .env ]; then
  note "跳过判官检查（缺 .env）"
else
  judge_provider=$(env_val JUDGEMENT_PROVIDER)
  judge_provider=${judge_provider:-none}
  case "$judge_provider" in
    none)
      note "判官关闭（none）—— 不产生推演，也不攒校准样本"
      ;;
    fake)
      ok "判官 = fake（确定性假实现，仅 CI 用）"
      ;;
    jev|laya)
      judge_base=$(env_val JUDGEMENT_BASE_URL)
      judge_model=$(env_val JUDGEMENT_MODEL)
      judge_key=$(env_val JUDGEMENT_API_KEY)
      if [ "$judge_provider" = "jev" ]; then
        judge_base=${judge_base:-https://api.typesafe.ai}
        if [ -z "$judge_key" ]; then
          bad "判官 = jev，但 .env 里 JUDGEMENT_API_KEY 为空"
        elif ! command -v curl >/dev/null 2>&1; then
          note "缺 curl，跳过云端判官连通性检查"
        else
          probe="$PWD/.cache/doctor-jev-models.json"
          mkdir -p "$PWD/.cache"
          curl_out=$(curl -s -o "$probe" -w '%{http_code} %{time_total}' --max-time 15 \
            -H "Authorization: Bearer $judge_key" -H 'Accept: application/json' \
            "$judge_base/v1/models" 2>/dev/null)
          code=${curl_out%% *}
          secs=${curl_out##* }
          if [ "$code" = "200" ]; then
            models=$(grep -o '"name":"[^"]*"' "$probe" | cut -d'"' -f4 | paste -sd, -)
            ok "云端判官可达（$judge_base，${secs}s，模型：${models:-未知}）"
          elif [ "$code" = "401" ] || [ "$code" = "403" ]; then
            bad "云端判官拒绝鉴权（HTTP $code）—— JUDGEMENT_API_KEY 可能已过期（本 key 2026-10-22 到期）"
          else
            note "云端判官不可达（HTTP ${code:-无响应}）—— 简报会静默降级为「不产生推演」"
          fi
        fi
      else
        judge_base=${judge_base:-http://127.0.0.1:8077}
        if ! command -v curl >/dev/null 2>&1; then
          note "缺 curl，跳过 Laya 连通性检查"
        elif curl -s --max-time 5 -o /dev/null "$judge_base/healthz" 2>/dev/null; then
          ok "本地 Laya 判官可达（$judge_base，模型：${judge_model:-未知}）"
        else
          note "本地 Laya 判官未启动（$judge_base）—— make laya-serve 起服务"
        fi
      fi
      ;;
    *)
      note "未知 JUDGEMENT_PROVIDER=$judge_provider（可选：none / fake / laya / jev）"
      ;;
  esac
fi

echo "== 采集新鲜度（worker 是否在跑）=="
# 教训（2026-10-17）：只有 db 在跑、api/worker 都停了 → 采集静默断了 3.8 天，
# 数据卡在 10-14，Pulse/Thread 和所有「最近 N 天」视图直接空掉。
# 关键：这个故障**不会让任何现有检查变红**——health 正常、测试全绿、简报照常生成
# （只是写「本期没有可用的新内容」）。所以必须单独查「最新文档有多旧」。
STALE_HOURS=${DOCTOR_STALE_HOURS:-12}
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  note "跳过采集新鲜度检查（docker 不可用）"
else
  latest=$(docker compose exec -T db psql -U humanpulse -d humanpulse -t -A -c \
    "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - max(COALESCE(published_at, fetched_at))))/3600, -1) FROM documents WHERE status='enriched';" \
    2>/dev/null | tr -d '[:space:]' || true)
  if [ -z "$latest" ]; then
    note "读不到采集新鲜度（栈未起或 DB 不可达）—— 若要查采集状态，make dev 起栈后复跑"
  else
    hours=${latest%%.*}
    case "$hours" in
      -1) note "库里没有 enriched 文档，无法判断新鲜度" ;;
      *)
        if [ "${hours:-0}" -ge "$STALE_HOURS" ]; then
          bad "采集已停滞 ${hours} 小时（阈值 ${STALE_HOURS}h）—— 检查 worker：docker compose ps"
        else
          ok "采集活跃：最新 enriched 文档 ${hours} 小时前"
        fi
        ;;
    esac
  fi
fi

echo "== compose 配置 =="
if [ -f .env ] && command -v docker >/dev/null 2>&1; then
  if docker compose -f docker-compose.yml config -q >/dev/null 2>&1; then ok "docker-compose.yml 可解析"
  else bad "docker-compose.yml 解析失败：docker compose -f docker-compose.yml config"; fi
  if docker compose -f docker-compose.prod.yml config -q >/dev/null 2>&1; then ok "docker-compose.prod.yml 可解析"
  else bad "docker-compose.prod.yml 解析失败（通常缺 DOMAIN / POSTGRES_PASSWORD）"; fi
else
  note "跳过 compose 校验（缺 .env 或 docker）"
fi

echo "== 端口 =="
for port in 5432 8000 5173; do
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    note "端口 $port 已被占用（若已在跑本项目的 compose 属正常）"
  else
    ok "端口 $port 空闲"
  fi
done

echo
if [ "$fail" -gt 0 ]; then
  echo "doctor: $fail 项必须修复，$warn 项警告"
  exit 1
fi
echo "doctor: 通过（$warn 项警告）"
