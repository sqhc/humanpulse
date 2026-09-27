"""聚类读取：同一事件的多来源报道。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.analysis import Analysis, Cluster, ClusterMember
from app.models.document import Document
from app.models.source import Source
from app.schemas.content import ClusterDetailOut, ClusterOut, DocumentOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _cluster_out(cluster: Cluster) -> ClusterOut:
    return ClusterOut(
        id=cluster.id,
        canonical_document_id=cluster.canonical_document_id,
        key_terms=list(cluster.key_terms or []),
        doc_count=cluster.doc_count,
        first_seen_at=cluster.first_seen_at,
        last_seen_at=cluster.last_seen_at,
    )


@router.get("/clusters", response_model=list[ClusterOut], summary="最近的聚类")
async def list_clusters(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    min_docs: Annotated[int, Query(ge=1, le=100)] = 1,
) -> list[ClusterOut]:
    stmt = (
        select(Cluster)
        .where(Cluster.doc_count >= min_docs)
        .order_by(Cluster.last_seen_at.desc())
        .limit(limit)
    )
    return [_cluster_out(c) for c in (await session.execute(stmt)).scalars().all()]


@router.get("/clusters/{cluster_id}", response_model=ClusterDetailOut, summary="聚类详情")
async def get_cluster(cluster_id: int, session: SessionDep) -> ClusterDetailOut:
    cluster = await session.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="聚类不存在")

    latest_analysis = (
        select(func.max(Analysis.id))
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(Document, Analysis, Source.name)
            .join(ClusterMember, ClusterMember.document_id == Document.id)
            .outerjoin(Analysis, Analysis.id == latest_analysis)
            .outerjoin(Source, Source.id == Document.source_id)
            .where(ClusterMember.cluster_id == cluster_id)
            .order_by(Document.id.desc())
            .limit(50)
        )
    ).all()

    documents = [
        DocumentOut(
            id=doc.id,
            url=doc.url,
            canonical_url=doc.canonical_url,
            title=doc.title,
            author=doc.author,
            source_id=doc.source_id,
            source_name=source_name,
            published_at=doc.published_at,
            fetched_at=doc.fetched_at,
            language=doc.language,
            kind=doc.kind,
            excerpt=doc.excerpt,
            status=doc.status,
            rejection_reason=doc.rejection_reason,
            score=analysis.score if analysis else None,
            summary_zh=analysis.summary_zh if analysis else None,
            summary_en=analysis.summary_en if analysis else None,
            tags=list(analysis.tags) if analysis else [],
            regions=list(analysis.regions) if analysis else [],
            rationale=analysis.rationale if analysis else None,
            cluster_id=cluster_id,
        )
        for doc, analysis, source_name in rows
    ]
    return ClusterDetailOut(**_cluster_out(cluster).model_dump(), documents=documents)
