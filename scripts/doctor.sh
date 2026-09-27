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
    bad "Node $node_major.$node_minor 过低（Vite 8 需要 >= 22.12 或 >= 20.19）"
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
