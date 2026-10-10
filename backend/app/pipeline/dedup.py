"""二级去重：向量近邻判定与聚类归并。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.analysis import Cluster, ClusterMember, Embedding
from app.models.document import Document


def is_duplicate(
    similarity: float,
    *,
    is_hot: bool,
    threshold: float,
    hot_threshold: float,
) -> bool:
    """热点内容的阈值更宽松（同一事件短时间被大量报道）。

    阈值本身可配置：放宽会合并更多报道、收紧会把同一事件拆成多条。
    """
    return similarity >= (hot_threshold if is_hot else threshold)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(slots=True)
class NearestMatch:
    document_id: int
    similarity: float
    is_hot: bool


def window_anchor(
    *,
    published_at: datetime | None,
    fetched_at: datetime | None,
    reference: datetime | None = None,
) -> datetime | None:
    """聚类时间窗的锚点。

    为什么不用墙钟：find_nearest 原来拿 datetime.now() 当窗口起点，实时采集时没问题，
    但 make reembed 是离线重放——如果最近一次采集是几天前，窗口内一篇文档都没有，
    结果每篇文档各自成簇（multi_doc_clusters=0），看起来像语义向量没用，
    实际是时间窗失效。锚点应以文档自身时间为主。

    取 coalesce(published_at, fetched_at)；两者都缺才退回 reference。
    另防脏数据：fetched_at 明显早于 published_at 时信任 published_at。
    """
    published = _as_utc(published_at)
    fetched = _as_utc(fetched_at)
    # 容错：抓取时间不该早于发布时间（时区错配或来源数据脏）
    if published is not None and fetched is not None and fetched < published - timedelta(days=1):
        return published
    return published or fetched or _as_utc(reference)


def is_recent(
    moment: datetime,
    *,
    reference: datetime | None = None,
    window_hours: int,
) -> bool:
    """moment 是否落在 reference 之前的 window_hours 内。

    与 window_anchor 同理：reference 默认墙钟（实时采集），
    离线重放时由调用方传入文档时间，热点判定才成立。
    """
    now = _as_utc(reference) or datetime.now(UTC)
    anchored = _as_utc(moment)
    return anchored is not None and anchored >= now - timedelta(hours=window_hours)


async def find_nearest(
    session: AsyncSession,
    vec: list[float],
    *,
    exclude_document_id: int,
    window_hours: int | None = None,
    anchor: datetime | None = None,
) -> NearestMatch | None:
    """在时间窗内找最相似的已入库文档（pgvector cosine 距离）。

    anchor 是时间窗的中心时刻：实时采集传 now（缺省），离线重建（reembed）传文档自身时间。
    若不传 anchor，重放几天前的老数据时窗口为空、聚类会整体失效（见 window_anchor）。
    """
    settings = get_settings()
    hours = window_hours or settings.vector_dup_window_hours
    reference = _as_utc(anchor) or datetime.now(UTC)
    since = reference - timedelta(hours=hours)
    until = reference + timedelta(hours=hours)

    distance = Embedding.vec.cosine_distance(vec)
    stmt = (
        select(
            Embedding.document_id,
            distance.label("distance"),
            Document.published_at,
            Document.fetched_at,
        )
        .join(Document, Document.id == Embedding.document_id)
        .where(Embedding.document_id != exclude_document_id)
        # 双向窗口：离线重放时 anchor 落在文档时间轴上，同批次一起入库的文档也要能看到
        .where(func.coalesce(Document.published_at, Document.fetched_at) >= since)
        .where(func.coalesce(Document.published_at, Document.fetched_at) <= until)
        .order_by(distance)
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None

    document_id, raw_distance, published_at, fetched_at = row
    moment = window_anchor(published_at=published_at, fetched_at=fetched_at, reference=reference)
    return NearestMatch(
        document_id=int(document_id),
        similarity=1.0 - float(raw_distance),
        # 热点判定同样相对 anchor：否则离线重建会把所有文档都当冷数据
        is_hot=is_recent(
            moment or reference,
            reference=reference,
            window_hours=settings.vector_dup_window_hours,
        ),
    )


async def cluster_of_document(session: AsyncSession, document_id: int) -> int | None:
    stmt = select(ClusterMember.cluster_id).where(ClusterMember.document_id == document_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def attach_cluster(
    session: AsyncSession,
    *,
    document: Document,
    vec: list[float],
    key_terms: list[str] | None = None,
) -> tuple[int, float | None]:
    """把文档挂到最近的 cluster，超出阈值则新建。返回 (cluster_id, similarity)。

    时间窗锚在**本文档的时间**上（而不是墙钟）：实时采集时两者几乎等价，
    但 reembed 离线重放老数据时，只有用文档时间才能聚起来。
    """
    settings = get_settings()
    now = window_anchor(
        published_at=document.published_at, fetched_at=document.fetched_at
    ) or datetime.now(UTC)
    nearest = await find_nearest(session, vec, exclude_document_id=document.id, anchor=now)

    if nearest is not None and is_duplicate(
        nearest.similarity,
        is_hot=nearest.is_hot,
        threshold=settings.vector_dup_threshold,
        hot_threshold=settings.vector_dup_threshold_hot,
    ):
        cluster_id = await cluster_of_document(session, nearest.document_id)
        if cluster_id is None:
            cluster = Cluster(
                canonical_document_id=nearest.document_id,
                key_terms=key_terms or [],
                first_seen_at=now,
                last_seen_at=now,
                doc_count=1,
            )
            session.add(cluster)
            await session.flush()
            cluster_id = cluster.id
            session.add(
                ClusterMember(
                    cluster_id=cluster_id, document_id=nearest.document_id, similarity=None
                )
            )
        existing_cluster = await session.get(Cluster, cluster_id)
        if existing_cluster is not None:
            existing_cluster.doc_count = (existing_cluster.doc_count or 0) + 1
            existing_cluster.last_seen_at = now
            if key_terms and not existing_cluster.key_terms:
                existing_cluster.key_terms = key_terms
        session.add(
            ClusterMember(
                cluster_id=cluster_id, document_id=document.id, similarity=nearest.similarity
            )
        )
        await session.flush()
        return cluster_id, nearest.similarity

    cluster = Cluster(
        canonical_document_id=document.id,
        key_terms=key_terms or [],
        first_seen_at=now,
        last_seen_at=now,
        doc_count=1,
    )
    session.add(cluster)
    await session.flush()
    session.add(ClusterMember(cluster_id=cluster.id, document_id=document.id, similarity=1.0))
    await session.flush()
    return cluster.id, None


def embedding_text(summary_zh: str, summary_en: str, tags: list[str], title: str) -> str:
    """送去向量化的文本：双语摘要 + 标签 + 标题（标题权重靠重复实现）。"""
    parts: list[Any] = [title, title, summary_zh, summary_en, " ".join(tags or [])]
    return "\n".join(str(p) for p in parts if p)
