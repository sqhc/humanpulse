#!/usr/bin/env bash
# 备份恢复演练：把 dump 恢复到临时库，校验后删除。详见 docs/runbook.md。
set -euo pipefail

cd "$(dirname "$0")/.."

DUMP="${DUMP:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "用法: make restore-drill DUMP=/path/to/backup.dump" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

DB_USER="${POSTGRES_USER:-humanpulse}"
TMP_DB="restore_drill_$(date +%s)"
COMPOSE="docker compose -f $COMPOSE_FILE"

cleanup() {
  echo "== 清理临时库 $TMP_DB =="
  $COMPOSE exec -T db dropdb -U "$DB_USER" --if-exists "$TMP_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== 创建临时库 $TMP_DB =="
$COMPOSE exec -T db createdb -U "$DB_USER" "$TMP_DB"

echo "== 从 $DUMP 恢复 =="
$COMPOSE exec -T db pg_restore -U "$DB_USER" -d "$TMP_DB" --no-owner --no-privileges < "$DUMP"

echo "== 校验 =="
$COMPOSE exec -T db psql -U "$DB_USER" -d "$TMP_DB" -c "select count(*) as tables from information_schema.tables where table_schema = 'public';"

echo "restore-drill: 通过（临时库已删除）"
echo "请把本次结果记入 docs/runbook.md 的演练记录表。"
