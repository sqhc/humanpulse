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

echo "== 生成日报与周报（fake LLM，不联网）=="
BRIEF_JSON=$($COMPOSE exec -T -e LLM_PROVIDER=fake -e EMBEDDING_PROVIDER=hash api python -m app.cli brief --force | tail -1)
echo "$BRIEF_JSON"
WEEKLY_JSON=$($COMPOSE exec -T -e LLM_PROVIDER=fake -e EMBEDDING_PROVIDER=hash api python -m app.cli brief --kind weekly --force | tail -1)
echo "$WEEKLY_JSON"

echo "== SSE 探活（只读前 3 行）=="
SSE_HEAD=$(curl -sS -N --max-time 4 "$BASE/stream" | head -3 || true)
echo "$SSE_HEAD"
echo "$SSE_HEAD" | grep -q "event: ready" || { echo "SSE 未返回 ready 帧" >&2; exit 1; }

echo '== 管理台实体候选接口（无 key 应 401，无效合并应 400）=='
ADMIN_KEY=$(grep -E '^ADMIN_API_KEY=' .env | cut -d= -f2-)
NO_KEY=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/admin/entity-candidates")
[ "$NO_KEY" = '401' ] || { echo "无 key 期望 401，实际 $NO_KEY" >&2; exit 1; }
CANDIDATES=$(curl -fsS -H "X-API-Key: $ADMIN_KEY" "$BASE/admin/entity-candidates")
echo "$CANDIDATES" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["alias_group_count"] >= 1, d; print("  候选", len(d["candidates"]), "| 别名组", d["alias_group_count"], "| 自检问题", d["alias_problems"])'
BAD=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "X-API-Key: $ADMIN_KEY" -H 'content-type: application/json' -d '{"merges":[{"canonical_id":999999,"alias_ids":[1]}]}' "$BASE/admin/entity-aliases/apply")
[ "$BAD" = '400' ] || { echo "无效合并期望 400，实际 $BAD" >&2; exit 1; }
echo "== 应用实体别名表（幂等）=="
$COMPOSE exec -T api python -m app.cli alias-apply | tail -1

echo "== 校验读取接口 =="
API_BASE="$BASE" ADMIN_KEY="$ADMIN_KEY" DEMO_JSON="$DEMO_JSON" BRIEF_JSON="$BRIEF_JSON" WEEKLY_JSON="$WEEKLY_JSON" python3 - <<'PY'
import json
import os
import urllib.parse
import urllib.request

base = os.environ["API_BASE"]
demo = json.loads(os.environ["DEMO_JSON"])
brief_job = json.loads(os.environ["BRIEF_JSON"])
weekly_job = json.loads(os.environ["WEEKLY_JSON"])

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

entities = get("/entities?limit=10")
# 别名行不应该出现在列表里（canonical_entity_id 非空的被过滤）
assert all(item["name"] for item in entities), "实体名为空"
assert len(entities) >= 1, "实体列表为空（流程里应写入 headless 实体）"
entity_detail = get(f"/entities/{entities[0]['id']}")
assert entity_detail["timeline"], "实体缺少时间线"
assert entity_detail["recent"], "实体缺少最近提及"

assert weekly_job["created"] is True, f"周报未生成: {weekly_job}"
weekly = get("/briefs/latest?kind=weekly")
assert weekly["title"], "周报缺少标题"
assert "## 来源清单" in weekly["markdown"], "周报缺少来源清单"
weekly_en = get_text(f"/briefs/{weekly['id']}/markdown?language=en")
assert weekly_en.startswith("#"), "周报英文重渲染失败"
weekly_list = get("/briefs?kind=weekly&limit=5")
assert len(weekly_list) >= 1, "周报列表为空"


key = os.environ.get("ADMIN_KEY", "")


def post(path: str, payload: dict):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as resp:
        return json.load(resp)


# 候选确认的真实路径：挑两个同类型实体合并（remember=False，只动这份一次性数据库）
by_kind: dict[str, list] = {}
for item in entities:
    by_kind.setdefault(item["kind"], []).append(item)
pair = next((group for group in by_kind.values() if len(group) >= 2), None)
merged_note = "skipped"
if pair:
    canonical, alias = pair[0], pair[1]
    result = post(
        "/admin/entity-aliases/apply",
        {"merges": [{"canonical_id": canonical["id"], "alias_ids": [alias["id"]]}], "remember": False},
    )
    assert result["merged"] >= 1, f"合并未生效: {result}"
    assert result["remembered"] is False, result
    after = get(f"/entities/{canonical['id']}")
    assert after["mention_count"] >= canonical["mention_count"], after
    merged_note = f"{result['merged']} 个 / 移动 {result['moved']} 条提及"

video = get("/briefs/%d/storyboard?language=zh" % brief["id"])
assert video["scene_count"] >= 2, f"脚本分镜太少: {video}"
assert video["total_seconds"] > 0, "脚本总时长为 0"
assert video["scenes"][0]["kind"] == "title", video["scenes"][0]
srt_text = get_text("/briefs/%d/subtitles.srt?language=zh" % brief["id"])
assert srt_text.startswith("1"), f"字幕格式异常: {srt_text[:40]}"
assert " --> " in srt_text, "字幕缺少时间轴"
print("接口校验通过：",
    {
        "documents": documents["total_returned"],
        "clusters": len(clusters),
        "sources": len(sources),
        "top_score": first["score"],
        "brief_items": brief["item_count"],
        "weekly_items": weekly["item_count"],
        "entities": len(entities),
        "alias_merge": merged_note,
        "scenes": video["scene_count"],
        "video_seconds": video["total_seconds"],
        "ingest": demo["ingest"],
    },
)
PY

echo "smoke: 通过"
