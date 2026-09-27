"""选材：一个事件（cluster）只留一条代表，避免同一事件刷屏。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis, ClusterMember
from app.models.document import Document
from app.models.source import Source


@dataclass(slots=True)
class SelectedItem:
    """进入简报的一条素材。"""

    document_id: int
    cluster_id: int | None
    title: str
    summary_zh: str
    summary_en: str
    score: int
    source_name: str | None
    url: str
    published_at: datetime | None
    headline_only: bool


def pick_representatives(items: list[SelectedItem], limit: int) -> list[SelectedItem]:
    """同一 cluster 只保留评分最高的一条；无 cluster 的各自保留。按评分降序取前 limit 条。"""
    best: dict[str, SelectedItem] = {}
    for item in items:
        key = f"c{item.cluster_id}" if item.cluster_id is not None else f"d{item.document_id}"
        current = best.get(key)
        if current is None or item.score > current.score:
            best[key] = item
    ranked = sorted(
        best.values(),
        key=lambda item: (item.score, item.published_at or datetime.min),
        reverse=True,
    )
    return ranked[:limit]


async def select_items(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    limit: int,
) -> list[SelectedItem]:
    """取时间窗内已富化的文档，去重后返回前 limit 条。"""
    latest_analysis = (
        select(func.max(Analysis.id))
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(Document, Analysis, ClusterMember.cluster_id, Source.name)
            .join(Analysis, Analysis.id == latest_analysis)
            .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
            .outerjoin(Source, Source.id == Document.source_id)
            .where(Document.status == "enriched")
            .where(func.coalesce(Document.published_at, Document.fetched_at) >= since)
            .where(func.coalesce(Document.published_at, Document.fetched_at) <= until)
            .order_by(Analysis.score.desc(), Document.id.asc())
            .limit(max(limit * 20, 200))
        )
    ).all()

    items = [
        SelectedItem(
            document_id=document.id,
            cluster_id=cluster_id,
            title=document.title,
            summary_zh=analysis.summary_zh or "",
            summary_en=analysis.summary_en or "",
            score=int(analysis.score or 0),
            source_name=source_name,
            url=document.url,
            published_at=document.published_at,
            headline_only="headline-only" in list(analysis.tags or []),
        )
        for document, analysis, cluster_id, source_name in rows
    ]
    return pick_representatives(items, limit)
