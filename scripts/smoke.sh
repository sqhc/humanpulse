#!/usr/bin/env bash
# 起栈 → 迁移 → 合成数据跑通流水线 → 校验读取接口 → 收栈。
#
# 设计要点：
#   * 用独立的 compose project（humanpulse-smoke）与端口，不动本地开发栈的数据；
#   * 全程 LLM_PROVIDER=fake / EMBEDDING_PROVIDER=hash：不联网、不产生费用；
#   * CI 与本地共用这一条路径。
set -euo pipefail

cd "$(dirname "$0")/.."

export API_PORT="${SMOKE_API_PORT:-18000}"
export POSTGRES_PORT="${SMOKE_POSTGRES_PORT:-15432}"
COMPOSE="docker compose -p humanpulse-smoke -f docker-compose.yml"
BASE="http://localhost:${API_PORT}/api/v1"

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

echo "== 清理上一次的冒烟环境（只影响 humanpulse-smoke） =="
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true

echo "== 构建并起栈 =="
$COMPOSE up -d --build --wait db api worker

echo "== 探活 /api/v1/health =="
for _ in $(seq 1 30); do
  if curl -fsS "$BASE/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$BASE/health"; echo
echo "== /api/v1/ready =="
curl -sS "$BASE/ready"; echo

echo "== 数据库迁移 =="
$COMPOSE exec -T api python -m app.cli migrate

echo "== 合成数据跑通采集 → 处理 → 聚类 =="
DEMO_JSON=$($COMPOSE exec -T -e LLM_PROVIDER=fake -e EMBEDDING_PROVIDER=hash api python -m app.cli demo | tail -1)
echo "$DEMO_JSON"

echo "== 生成日报（fake LLM，不联网）=="
BRIEF_JSON=$($COMPOSE exec -T -e LLM_PROVIDER=fake -e EMBEDDING_PROVIDER=hash api python -m app.cli brief --force | tail -1)
echo "$BRIEF_JSON"

echo "== 校验读取接口 =="
API_BASE="$BASE" DEMO_JSON="$DEMO_JSON" BRIEF_JSON="$BRIEF_JSON" python3 - <<'PY'
import json
import os
import urllib.parse
import urllib.request

base = os.environ["API_BASE"]
demo = json.loads(os.environ["DEMO_JSON"])
brief_job = json.loads(os.environ["BRIEF_JSON"])

assert demo["ingest"]["new"] >= 2, f"采集未产生新文档: {demo}"
assert demo["ingest"]["near_duplicate"] >= 1, f"SimHash 未拦截镜像: {demo}"
assert demo["process"]["enriched"] >= 2, f"处理未富化: {demo}"
assert demo["clusters"] >= 1, f"未产生聚类: {demo}"


def get(path: str):
    with urllib.request.urlopen(base + path, timeout=20) as resp:
        return json.load(resp)


def get_text(path: str) -> str:
    with urllib.request.urlopen(base + path, timeout=20) as resp:
        return resp.read().decode("utf-8")


documents = get("/documents?limit=5")
assert documents["total_returned"] >= 2, f"documents 不足: {documents}"
first = documents["items"][0]
assert first["summary_zh"], "缺少中文摘要"
assert first["score"] is not None, "缺少评分"
assert first["cluster_id"] is not None, "缺少聚类归属"

clusters = get("/clusters")
assert len(clusters) >= 1, "clusters 为空"

detail = get(f"/documents/{first['id']}")
assert detail["id"] == first["id"]

sources = get("/sources")
assert len(sources) >= 1, "sources 为空"

tag = first["tags"][0] if first["tags"] else None
if tag:
    filtered = get(f"/documents?limit=5&tag={urllib.parse.quote(tag)}")
    assert filtered["total_returned"] >= 1, f"按标签过滤失败: {tag}"

assert brief_job["created"] is True, f"日报未生成: {brief_job}"
assert brief_job["item_count"] >= 2, f"日报素材不足: {brief_job}"

brief = get("/briefs/latest")
assert brief["markdown"].startswith("#"), "日报缺少标题"
assert "## 来源清单" in brief["markdown"], "日报缺少来源清单"
assert brief["structured"].get("sections"), "日报缺少结构化分组"

english = get_text(f"/briefs/{brief['id']}/markdown?language=en")
assert english.startswith("#"), "英文重渲染失败"
assert "## Sources" in english or "## " in english, "英文重渲染缺少分组"

briefs = get("/briefs?kind=daily&limit=5")
assert len(briefs) >= 1, "简报列表为空"

print(
    "接口校验通过：",
    {
        "documents": documents["total_returned"],
        "clusters": len(clusters),
        "sources": len(sources),
        "top_score": first["score"],
        "brief_items": brief["item_count"],
        "ingest": demo["ingest"],
    },
)
PY

echo "smoke: 通过"
