#!/usr/bin/env bash
# 起栈 → 探活 → 收栈。CI 与本地都用这一条路径。
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml"
PORT="${API_PORT:-8000}"

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon 不可用，请先启动 Docker Desktop" >&2
  exit 1
fi

[ -f .env ] || cp .env.example .env

cleanup() {
  echo "== 收栈 =="
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== 构建并起栈 =="
$COMPOSE up -d --build --wait db api worker

echo "== 探活 /api/v1/health =="
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:$PORT/api/v1/health" >/dev/null 2>&1; then
    curl -fsS "http://localhost:$PORT/api/v1/health"
    echo
    echo "== /api/v1/ready =="
    curl -sS "http://localhost:$PORT/api/v1/ready" || true
    echo
    echo "smoke: 通过"
    exit 0
  fi
  sleep 2
done

echo "smoke: 探活超时，最近的日志：" >&2
$COMPOSE logs --tail=80 api db >&2 || true
exit 1
