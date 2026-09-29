"""实体与时间线：谁/哪个组织在这段时间里被反复提及。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.analysis import Analysis, ClusterMember
from app.models.document import Document
from app.models.entity import Entity, EntityMention
from app.models.source import Source
from app.schemas.content import EntityDetailOut, EntityMentionOut, EntityOut, EntityTimelinePoint

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _entity_out(entity: Entity) -> EntityOut:
    return EntityOut(
        id=entity.id,
        name=entity.name,
        kind=entity.kind,
        aliases=list(entity.aliases or []),
        mention_count=entity.mention_count,
        first_seen_at=entity.first_seen_at,
        last_seen_at=entity.last_seen_at,
    )


@router.get("/entities", response_model=list[EntityOut], summary="实体列表（可按名字搜索）")
async def list_entities(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=80)] = None,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    order: Annotated[str, Query(pattern="^(mentions|recent)$")] = "mentions",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[EntityOut]:
    # 只列出规范实体：别名行（canonical_entity_id 非空）保留用于审计，但不再作为独立实体展示
    stmt = (
        select(Entity).where(Entity.mention_count > 0).where(Entity.canonical_entity_id.is_(None))
    )
    if q:
        stmt = stmt.where(Entity.name.ilike(f"%{q}%"))
    if kind:
        stmt = stmt.where(Entity.kind == kind)
    if order == "recent":
        stmt = stmt.order_by(Entity.last_seen_at.desc())
    else:
        stmt = stmt.order_by(Entity.mention_count.desc(), Entity.last_seen_at.desc())
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [_entity_out(entity) for entity in rows]


@router.get("/entities/{entity_id}", response_model=EntityDetailOut, summary="实体详情与时间线")
async def get_entity(
    entity_id: int,
    session: SessionDep,
    days: Annotated[int, Query(ge=7, le=365)] = 90,
    recent_limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> EntityDetailOut:
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="实体不存在")

    since = datetime.now(UTC) - timedelta(days=days)
    moment = func.coalesce(Document.published_at, Document.fetched_at)
    day = func.date_trunc("day", moment).label("day")

    timeline_rows = (
        await session.execute(
            select(day, func.count().label("count"))
            # SELECT 里没有显式列出来自哪张表，必须给 SQLAlchemy 一个明确的左表
            .select_from(EntityMention)
            .join(Document, Document.id == EntityMention.document_id)
            .where(EntityMention.entity_id == entity_id)
            .where(moment >= since)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    timeline = [
        EntityTimelinePoint(day=value.strftime("%Y-%m-%d"), count=int(count))
        for value, count in timeline_rows
        if value is not None
    ]

    latest_analysis = (
        select(func.max(Analysis.id))
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    recent_rows = (
        await session.execute(
            select(
                Document, Analysis, Source.name, EntityMention.salience, ClusterMember.cluster_id
            )
            .join(EntityMention, EntityMention.document_id == Document.id)
            .outerjoin(Analysis, Analysis.id == latest_analysis)
            .outerjoin(Source, Source.id == Document.source_id)
            .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
            .where(EntityMention.entity_id == entity_id)
            .order_by(moment.desc())
            .limit(recent_limit)
        )
    ).all()
    recent = [
        EntityMentionOut(
            document_id=document.id,
            title=document.title,
            url=document.url,
            source_name=source_name,
            published_at=document.published_at or document.fetched_at,
            score=analysis.score if analysis else None,
            cluster_id=cluster_id,
            salience=float(salience or 0),
        )
        for document, analysis, source_name, salience, cluster_id in recent_rows
    ]

    return EntityDetailOut(**_entity_out(entity).model_dump(), timeline=timeline, recent=recent)
