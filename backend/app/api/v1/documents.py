"""Feed 与详情：只读接口，公开访问。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.db import get_session
from app.models.analysis import Analysis, ClusterMember, Embedding
from app.models.document import Document
from app.models.source import Source
from app.schemas.content import DocumentDetailOut, DocumentListOut, DocumentOut, EntityRef

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _to_out(
    document: Document,
    analysis: Analysis | None,
    cluster_id: int | None,
    source_name: str | None,
) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        url=document.url,
        canonical_url=document.canonical_url,
        title=document.title,
        author=document.author,
        source_id=document.source_id,
        source_name=source_name,
        published_at=document.published_at,
        fetched_at=document.fetched_at,
        language=document.language,
        kind=document.kind,
        excerpt=document.excerpt,
        status=document.status,
        rejection_reason=document.rejection_reason,
        score=analysis.score if analysis else None,
        summary_zh=analysis.summary_zh if analysis else None,
        summary_en=analysis.summary_en if analysis else None,
        tags=list(analysis.tags) if analysis else [],
        regions=list(analysis.regions) if analysis else [],
        entities=[
            EntityRef(
                name=str(entry.get("name", "")).strip(),
                kind=str(entry.get("kind", "org")),
                salience=float(entry.get("salience", 0) or 0),
            )
            for entry in (analysis.entities or [])
            if isinstance(entry, dict) and entry.get("name")
        ]
        if analysis
        else [],
        rationale=analysis.rationale if analysis else None,
        cluster_id=cluster_id,
    )


def _latest_analysis_id() -> ScalarSelect[Any]:
    return (
        select(func.max(Analysis.id))
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )


@router.get("/documents", response_model=DocumentListOut, summary="Feed（游标分页）")
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[int | None, Query(ge=1, description="上一页最后一条的 id")] = None,
    doc_status: Annotated[str, Query(alias="status")] = "enriched",
    lang: Annotated[str | None, Query(max_length=8)] = None,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    region: Annotated[str | None, Query(max_length=40)] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    cluster_id: Annotated[int | None, Query(ge=1)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> DocumentListOut:
    latest_analysis = _latest_analysis_id()
    stmt = (
        select(Document, Analysis, ClusterMember.cluster_id, Source.name)
        .outerjoin(Analysis, Analysis.id == latest_analysis)
        .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
        .outerjoin(Source, Source.id == Document.source_id)
        .where(Document.status == doc_status)
    )
    if cursor is not None:
        stmt = stmt.where(Document.id < cursor)
    if lang:
        stmt = stmt.where(Document.language == lang)
    if kind:
        stmt = stmt.where(Document.kind == kind)
    if since:
        stmt = stmt.where(func.coalesce(Document.published_at, Document.fetched_at) >= since)
    if until:
        stmt = stmt.where(func.coalesce(Document.published_at, Document.fetched_at) <= until)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%"))
    if tag:
        stmt = stmt.where(Analysis.tags.contains([tag.lower()]))
    if region:
        stmt = stmt.where(Analysis.regions.contains([region.lower()]))
    if min_score is not None:
        stmt = stmt.where(Analysis.score >= min_score)
    if cluster_id is not None:
        stmt = stmt.where(ClusterMember.cluster_id == cluster_id)

    stmt = stmt.order_by(Document.id.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        _to_out(doc, analysis, cluster, source_name) for doc, analysis, cluster, source_name in rows
    ]
    return DocumentListOut(
        items=items,
        next_cursor=items[-1].id if has_more and items else None,
        total_returned=len(items),
    )


@router.get("/documents/{document_id}", response_model=DocumentDetailOut, summary="文档详情")
async def get_document(document_id: int, session: SessionDep) -> DocumentDetailOut:
    latest_analysis = _latest_analysis_id()
    row = (
        await session.execute(
            select(Document, Analysis, ClusterMember.cluster_id, Source.name)
            .outerjoin(Analysis, Analysis.id == latest_analysis)
            .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
            .outerjoin(Source, Source.id == Document.source_id)
            .where(Document.id == document_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    document, analysis, cluster_id, source_name = row
    base = _to_out(document, analysis, cluster_id, source_name)

    siblings: list[DocumentOut] = []
    if cluster_id is not None:
        sibling_rows = (
            await session.execute(
                select(Document, Analysis, ClusterMember.cluster_id, Source.name)
                .join(ClusterMember, ClusterMember.document_id == Document.id)
                .outerjoin(Analysis, Analysis.id == latest_analysis)
                .outerjoin(Source, Source.id == Document.source_id)
                .where(ClusterMember.cluster_id == cluster_id)
                .where(Document.id != document_id)
                .order_by(Document.id.desc())
                .limit(10)
            )
        ).all()
        siblings = [_to_out(doc, ana, cl, sname) for doc, ana, cl, sname in sibling_rows]

    return DocumentDetailOut(**base.model_dump(), siblings=siblings)


@router.get("/documents/{document_id}/embedding-dim", include_in_schema=False)
async def embedding_dim(document_id: int, session: SessionDep) -> dict[str, int | None]:
    """调试用：确认向量确实写入了（Phase 1 的自检接口）。"""
    stmt = select(Embedding.dim).where(Embedding.document_id == document_id)
    return {"document_id": document_id, "dim": (await session.execute(stmt)).scalar_one_or_none()}
