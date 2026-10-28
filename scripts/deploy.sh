#!/usr/bin/env bash
# VPS 上执行：拉取镜像并滚动重启。详见 docs/runbook.md。
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"

if [ ! -f .env ]; then
  echo "缺少 .env —— 请先按 docs/runbook.md 配置" >&2
  exit 1
fi

if [ -n "${DEPLOY_HOST:-}" ]; then
  echo "== 远程部署到 $DEPLOY_HOST =="
  : "${DEPLOY_USER:=root}"
  : "${DEPLOY_PATH:=/opt/humanpulse}"
  ssh "$DEPLOY_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && git pull --ff-only && TAG=${TAG:-latest} docker compose -f $COMPOSE_FILE pull && TAG=${TAG:-latest} docker compose -f $COMPOSE_FILE up -d --remove-orphans && docker compose -f $COMPOSE_FILE ps"
  exit 0
fi

echo "== 本机（VPS）部署 =="
docker compose -f "$COMPOSE_FILE" pull
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose -f "$COMPOSE_FILE" ps

# 启用 Oray PeanutHull 隧道 (如果安装)
if command -v hsk-cli &> /dev/null; then
  echo "🌐 Setting up Oray tunnel..."
  hsk-cli map 8000
fi

echo
echo "提示：设置 DEPLOY_HOST/DEPLOY_USER/DEPLOY_PATH 可从本地一键推送部署。"

