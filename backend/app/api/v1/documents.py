"""Feed 与详情：只读接口，公开访问。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.db import get_session
from app.models.analysis import Analysis, ClusterMember, Embedding
from app.models.document import Document
from app.models.source import Source
from app.pipeline import novelty as novelty_core
from app.pipeline import novelty_cohort
from app.schemas.content import (
    DocumentDetailOut,
    DocumentListOut,
    DocumentNoveltyOut,
    DocumentOut,
    EntityRef,
    NoveltyCohortOut,
    NoveltyFactorOut,
    NoveltyNeighbourOut,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

NEIGHBOUR_LIMIT = 10


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


@router.get(
    "/documents/{document_id}/novelty",
    response_model=DocumentNoveltyOut,
    summary="文档级 novelty / 信噪比（Signal）",
)
async def get_document_novelty(
    document_id: int,
    session: SessionDep,
    window_days: Annotated[int, Query(ge=1, le=90, description="时间窗天数")] = (
        novelty_core.HORIZON_DAYS
    ),
    tau_hours: Annotated[float, Query(gt=0, le=720, description="时间衰减常数（小时）")] = (
        novelty_core.TAU_HOURS
    ),
) -> DocumentNoveltyOut:
    """判断「这篇是不是**相对**新的信息」。

    确定性指标：窗口内最相似报道（pgvector 余弦，走 HNSW）、与它的时间间隔、来源分布、时效。
    不依赖聚类质量——93% 的 cluster 只有一篇，所以这是文档级而非 cluster 级判断。
    档位按分位数（p75/p25）相对切分，**不是绝对校准**：响应固定 `calibrated=False`，
    前端必须按「相对口径 + 未经校准」呈现。
    """
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    anchor = document.published_at or document.fetched_at
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    since = anchor - timedelta(days=window_days)

    vector = (
        await session.execute(select(Embedding.vec).where(Embedding.document_id == document_id))
    ).scalar_one_or_none()

    # 窗口内的近邻：先按余弦距离取前 N（HNSW 生效），再回落成可解释的邻居清单。
    # 时间条件写在 WHERE 里，HNSW 会在过滤后返回结果——召回可能略降，但精度不受影响，
    # 且本接口只做「有没有高度相似报道」的排序判断，不要求严格 top-k 完备。
    neighbours: list[NoveltyNeighbourOut] = []
    nearest_hours: float | None = None
    max_similarity: float | None = None
    if vector is not None:
        distance = Embedding.vec.cosine_distance(vector).label("distance")
        neighbour_rows = (
            await session.execute(
                select(Document, Source.name, distance)
                .join(Embedding, Embedding.document_id == Document.id)
                .outerjoin(Source, Source.id == Document.source_id)
                .where(Embedding.document_id != document_id)
                .where(Document.status == "enriched")
                .where(func.coalesce(Document.published_at, Document.fetched_at) >= since)
                .where(func.coalesce(Document.published_at, Document.fetched_at) <= anchor)
                .order_by(distance)
                .limit(NEIGHBOUR_LIMIT)
            )
        ).all()
        for neighbour, neighbour_source, raw_distance in neighbour_rows:
            similarity = 1.0 - float(raw_distance or 0.0)
            moment = neighbour.published_at or neighbour.fetched_at
            if moment is not None and moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            neighbours.append(
                NoveltyNeighbourOut(
                    document_id=neighbour.id,
                    title=neighbour.title,
                    url=neighbour.url,
                    source_name=neighbour_source,
                    similarity=round(similarity, 4),
                    published_at=moment,
                )
            )
        if neighbours:
            max_similarity = neighbours[0].similarity
            if neighbours[0].published_at is not None:
                nearest_hours = novelty_core.hours_between(neighbours[0].published_at, anchor)

    # 窗口内的来源分布：同源重复报道越多，这条越可能是「已被覆盖」。
    window_rows = (
        await session.execute(
            select(Document.source_id, func.count())
            .where(Document.id != document_id)
            .where(Document.status == "enriched")
            .where(func.coalesce(Document.published_at, Document.fetched_at) >= since)
            .where(func.coalesce(Document.published_at, Document.fetched_at) <= anchor)
            .group_by(Document.source_id)
        )
    ).all()
    total_in_window = sum(int(count) for _, count in window_rows)
    same_source = next(
        (int(count) for source_id, count in window_rows if source_id == document.source_id), 0
    )

    age_days = novelty_core.age_days_between(anchor, datetime.now(UTC)) if anchor else None

    result = novelty_core.compute_novelty(
        max_similarity=max_similarity,
        nearest_hours=nearest_hours,
        same_source=same_source,
        total_in_window=total_in_window,
        age_days=age_days,
        has_embedding=vector is not None,
        tau_hours=tau_hours,
    )
    # 档位/百分位来自**缓存的全局分布**：这是全局统计而非单文档属性，重建要跑全库，
    # 不能每请求算一次（见 pipeline/novelty_cohort.py 的取舍说明）。
    cohort_snapshot = await novelty_cohort.get_cohort(
        session, window_days=window_days, tau_hours=tau_hours
    )
    cohort = cohort_snapshot.cohort
    percentile = cohort.percentile_of(result.score)
    band = cohort.band_of(result.score)
    rec_zh, rec_en = novelty_core.recommendation(band, percentile)

    return DocumentNoveltyOut(
        document_id=document_id,
        novelty_score=result.score,
        percentile=percentile,
        band=band,
        factor_breakdown=[
            NoveltyFactorOut(
                key=factor.key,
                label_zh=factor.label_zh,
                label_en=factor.label_en,
                value=None if factor.value is None else round(factor.value, 4),
                weight=factor.weight,
                contribution=round(factor.contribution, 4),
                detail_zh=factor.detail_zh,
                detail_en=factor.detail_en,
            )
            for factor in result.factors
        ],
        neighbours=neighbours,
        window_days=window_days,
        tau_hours=tau_hours,
        cohort=NoveltyCohortOut(
            size=cohort.size,
            p25=round(cohort.low, 4),
            p75=round(cohort.high, 4),
            fallback=cohort.fallback,
            age_seconds=cohort_snapshot.age_seconds,
            ttl_seconds=cohort_snapshot.ttl_seconds,
        ),
        weights={
            "newness": novelty_core.W_NEWNESS,
            "time_freshness": novelty_core.W_TIME_FRESHNESS,
            "source_diversity": novelty_core.W_SOURCE_DIVERSITY,
            "recency": novelty_core.W_RECENCY,
        },
        recommendation_zh=rec_zh,
        recommendation_en=rec_en,
        basis_zh=result.basis_zh,
        basis_en=result.basis_en,
        confidence=result.confidence,
        calibrated=False,
        note_zh=novelty_core.NOTE_ZH,
        note_en=novelty_core.NOTE_EN,
    )
