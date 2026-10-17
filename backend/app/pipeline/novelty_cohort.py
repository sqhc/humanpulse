"""Signal novelty 的**全局分布缓存**（p25/p75 + 排名用的分数表）。

为什么需要它：单文档 novelty 的分数本身只要毫秒级；但「这条排在近期报道的第几百分位」
是**全局统计**，逐篇查库重建实测要秒级，超了 0.5s 预算。分布变化很慢（新文档按天进），
所以 TTL 缓存 + 惰性刷新是正解：过期后第一个请求触发重建，其余请求继续用旧值。

键 = (window_days, tau_hours)：换个窗口就是**另一个分布**，不能复用同一组切点。

**口径必须与端点一致**：cohort 里每篇的分数用与 `/documents/{id}/novelty` 完全相同的
因子函数与相同的缺席处理（core.compute_novelty），否则百分位是按另一把尺子算的。
参考时刻取「现在」算 age，与端点相同。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline import novelty as core

log = structlog.get_logger("pipeline.novelty_cohort")

# 一次查完全库：每篇 enriched 文档的最近邻（ORDER BY <=> LIMIT 1）。
#
# 注意（EXPLAIN 实测，956 行的库）：**规划器不会走 ix_embeddings_vec_hnsw**，
# 而是全表扫描 + top-N 排序——因为这个规模下顺序扫描更便宜（实测 0.3ms；
# SET enable_seqscan=off 强制走 HNSW 反而要 18.6ms）。索引 valid/ready 都是 true，
# 数据量上去后规划器会自己切过去，所以这里不需要也不应该硬指定索引。
# 真实约束是**行数**而非索引：全库重建 ~956 次近邻查询，才是要缓存的原因。
# 时间窗锚在**该文档自身时间**上，与单文档端点一致（实时与离线重放都能成立）。
_COHORT_SQL = text(
    """
    SELECT d.id,
           d.source_id,
           COALESCE(d.published_at, d.fetched_at) AS anchor,
           nb.similarity,
           nb.moment
    FROM documents d
    JOIN embeddings e ON e.document_id = d.id
    LEFT JOIN LATERAL (
        SELECT 1 - (e2.vec <=> e.vec) AS similarity,
               COALESCE(d2.published_at, d2.fetched_at) AS moment
        FROM embeddings e2
        JOIN documents d2 ON d2.id = e2.document_id
        WHERE e2.document_id <> d.id
          AND d2.status = 'enriched'
          AND COALESCE(d2.published_at, d2.fetched_at)
              BETWEEN COALESCE(d.published_at, d.fetched_at)
                  - make_interval(days => CAST(:window_days AS integer))
                  AND COALESCE(d.published_at, d.fetched_at)
        ORDER BY e2.vec <=> e.vec
        LIMIT 1
    ) nb ON true
    WHERE d.status = 'enriched'
    """
)


@dataclass
class _Entry:
    cohort: core.Cohort
    # 每篇的分数与 cohort 一起缓存：Feed 列表要按 id 取分，没有这张表就得每请求重算全库。
    scores: dict[int, float]
    stored_at: float


@dataclass(frozen=True)
class CohortSnapshot:
    """分布快照 + 它的新鲜度，供响应暴露「这个百分位是在什么分布上算的」。"""

    cohort: core.Cohort
    scores: dict[int, float]
    age_seconds: float
    ttl_seconds: int


_cache: dict[tuple[int, float], _Entry] = {}
_locks: dict[tuple[int, float], asyncio.Lock] = {}
_guard = asyncio.Lock()
TTL_SECONDS = core.COHORT_TTL_SECONDS


async def _lock_for(key: tuple[int, float]) -> asyncio.Lock:
    async with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _locks[key] = lock
        return lock


def clear_cohort_cache() -> None:
    """测试与运维用：清掉缓存强制重建。"""
    _cache.clear()
    _locks.clear()


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


async def score_documents(
    session: AsyncSession, *, window_days: int, tau_hours: float
) -> dict[int, float]:
    """全库算一遍每篇 enriched 文档的 novelty 分数（两处共用的唯一实现）。

    返回 {document_id: score}。这是**重活**（实测 ~1s / 956 篇），只应从
    `build_cohort` 的 TTL 缓存路径调用，别在请求里直接调。
    """
    raw = (await session.execute(_COHORT_SQL, {"window_days": window_days})).all()

    # 先整表读进内存（~千行），再逐篇算；避免每篇都发一次来源分布查询。
    prepared: list[tuple[int, int | None, datetime, float | None, datetime | None]] = []
    for document_id, source_id, anchor, similarity, moment in raw:
        anchor_moment = _aware(anchor)
        if anchor_moment is None:
            continue
        prepared.append(
            (
                int(document_id),
                source_id,
                anchor_moment,
                None if similarity is None else float(similarity),
                _aware(moment),
            )
        )
    # 按发布时间排序，让下面 _source_mix 的扫描能提前剪枝（见该函数注释）
    prepared.sort(key=lambda row: row[2])
    anchors = [row[2].timestamp() for row in prepared]

    now = datetime.now(UTC)
    scores: dict[int, float] = {}
    for index, (document_id, source_id, anchor, similarity, neighbour_moment) in enumerate(
        prepared
    ):
        same_source, total = _source_mix(prepared, anchors, index, source_id, anchor, window_days)
        score = core.compute_novelty(
            max_similarity=similarity,
            nearest_hours=(
                None if neighbour_moment is None else core.hours_between(neighbour_moment, anchor)
            ),
            same_source=same_source,
            total_in_window=total,
            age_days=max(0.0, core.age_days_between(anchor, now)),
            has_embedding=True,
            tau_hours=tau_hours,
        )
        scores[document_id] = score.score
    return scores


async def build_cohort(session: AsyncSession, *, window_days: int, tau_hours: float) -> _Entry:
    """全量重算并构成分布。"""
    scores = await score_documents(session, window_days=window_days, tau_hours=tau_hours)

    cohort = core.cohort_from_scores(
        list(scores.values()), window_days=window_days, tau_hours=tau_hours
    )
    log.info(
        "novelty_cohort_built",
        size=cohort.size,
        window_days=window_days,
        tau_hours=tau_hours,
        p25=round(cohort.low, 4),
        p75=round(cohort.high, 4),
        fallback=cohort.fallback,
    )
    return _Entry(cohort=cohort, scores=scores, stored_at=time.monotonic())


def _source_mix(
    prepared: list[tuple[int, int | None, datetime, float | None, datetime | None]],
    anchors: list[float],
    index: int,
    source_id: int | None,
    anchor: datetime,
    window_days: int,
) -> tuple[int, int]:
    """(同源条数, 窗口内总数)，不含自己。

    prepared 已按发布时间升序：窗口是 [anchor-W, anchor]，所以只需从 anchor 往回扫，
    遇到早于窗口下界的就可以停——纯内存操作，n≈956 时可忽略。
    """
    since = anchor.timestamp() - window_days * 86400.0
    until = anchor.timestamp()
    same_source = 0
    total = 0
    for other_index in range(index, -1, -1):
        stamp = anchors[other_index]
        if stamp < since:
            break
        if other_index == index:
            continue
        if stamp <= until:
            other_source = prepared[other_index][1]
            total += 1
            if source_id is not None and other_source == source_id:
                same_source += 1
    return same_source, total


async def get_cohort(
    session: AsyncSession, *, window_days: int, tau_hours: float, ttl_seconds: int | None = None
) -> CohortSnapshot:
    """取（必要时惰性重建）分布。TTL 内直接命中；过期时重建一次，其余请求仍读旧值。"""
    key = (window_days, float(tau_hours))
    ttl = TTL_SECONDS if ttl_seconds is None else ttl_seconds

    def snapshot(entry: _Entry) -> CohortSnapshot:
        return CohortSnapshot(
            cohort=entry.cohort,
            scores=entry.scores,
            age_seconds=round(max(0.0, time.monotonic() - entry.stored_at), 1),
            ttl_seconds=ttl,
        )

    entry = _cache.get(key)
    if entry is not None and (time.monotonic() - entry.stored_at) < ttl:
        return snapshot(entry)

    lock = await _lock_for(key)
    async with lock:
        entry = _cache.get(key)
        if entry is not None and (time.monotonic() - entry.stored_at) < ttl:
            return snapshot(entry)
        fresh = await build_cohort(session, window_days=window_days, tau_hours=tau_hours)
        _cache[key] = fresh
        return snapshot(fresh)
