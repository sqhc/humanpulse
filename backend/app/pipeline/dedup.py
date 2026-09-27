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


async def find_nearest(
    session: AsyncSession,
    vec: list[float],
    *,
    exclude_document_id: int,
    window_hours: int | None = None,
) -> NearestMatch | None:
    """在时间窗内找最相似的已入库文档（pgvector cosine 距离）。"""
    settings = get_settings()
    hours = window_hours or settings.vector_dup_window_hours
    since = datetime.now(UTC) - timedelta(hours=hours)

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
        .where(func.coalesce(Document.published_at, Document.fetched_at) >= since)
        .order_by(distance)
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None

    document_id, raw_distance, published_at, fetched_at = row
    moment = _as_utc(published_at) or _as_utc(fetched_at) or datetime.now(UTC)
    return NearestMatch(
        document_id=int(document_id),
        similarity=1.0 - float(raw_distance),
        is_hot=moment >= datetime.now(UTC) - timedelta(hours=settings.vector_dup_window_hours),
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
    """把文档挂到最近的 cluster，超出阈值则新建。返回 (cluster_id, similarity)。"""
    settings = get_settings()
    now = datetime.now(UTC)
    nearest = await find_nearest(session, vec, exclude_document_id=document.id)

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
