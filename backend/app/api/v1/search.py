"""语义搜索：用与入库同一套 embedder 把查询向量化，走 pgvector 的 HNSW 索引。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.embedding import get_embedder
from app.models.analysis import Analysis, ClusterMember, Embedding
from app.models.document import Document
from app.models.source import Source
from app.schemas.content import SearchHitOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/search", response_model=list[SearchHitOut], summary="语义搜索（向量近邻）")
async def search_documents(
    session: SessionDep,
    q: Annotated[str, Query(min_length=2, max_length=200, description="自然语言查询")],
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    min_similarity: Annotated[float, Query(ge=0.0, le=1.0)] = 0.2,
) -> list[SearchHitOut]:
    """按向量相似度找记录。

    搜索质量取决于 EMBEDDING_PROVIDER：hash 只是可复现的占位实现，
    生产应使用 local（见 ADR-0003）。
    """
    text = " ".join(q.split())
    if len(text) < 2:
        raise HTTPException(status_code=400, detail="查询太短")

    query_vector = get_embedder().embed(text)
    distance = Embedding.vec.cosine_distance(query_vector).label("distance")
    latest_analysis = (
        select(Analysis.id)
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(Document, Analysis, Source.name, ClusterMember.cluster_id, distance)
            .join(Embedding, Embedding.document_id == Document.id)
            .outerjoin(Analysis, Analysis.id == latest_analysis)
            .outerjoin(Source, Source.id == Document.source_id)
            .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
            .where(Document.status == "enriched")
            .order_by(distance)
            .limit(limit * 3)
        )
    ).all()

    hits: list[SearchHitOut] = []
    seen: set[int] = set()
    for document, analysis, source_name, cluster_id, raw_distance in rows:
        if document.id in seen:
            continue
        similarity = 1.0 - float(raw_distance or 0.0)
        if similarity < min_similarity:
            continue
        seen.add(document.id)
        hits.append(
            SearchHitOut(
                document_id=document.id,
                title=document.title,
                url=document.url,
                source_name=source_name,
                language=document.language,
                published_at=document.published_at or document.fetched_at,
                score=analysis.score if analysis else None,
                summary_zh=analysis.summary_zh if analysis else None,
                summary_en=analysis.summary_en if analysis else None,
                tags=list(analysis.tags or []) if analysis else [],
                cluster_id=cluster_id,
                similarity=round(similarity, 4),
            )
        )
        if len(hits) >= limit:
            break
    return hits
