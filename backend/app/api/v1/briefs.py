"""简报读取接口：列表、最新、详情、Markdown 渲染。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.briefs.render import render_markdown
from app.briefs.schema import BriefContent
from app.briefs.select import SelectedItem
from app.db import get_session
from app.models.analysis import ClusterMember
from app.models.document import Document
from app.models.source import Source
from app.models.summary import Brief, BriefItem
from app.schemas.content import BriefListItem, BriefOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _item_count_subquery() -> ScalarSelect[int]:
    return (
        select(func.count())
        .select_from(BriefItem)
        .where(BriefItem.brief_id == Brief.id)
        .correlate(Brief)
        .scalar_subquery()
    )


def _to_out(brief: Brief, item_count: int) -> BriefOut:
    return BriefOut(
        id=brief.id,
        kind=brief.kind,
        period_start=brief.period_start,
        period_end=brief.period_end,
        language=brief.language,
        title=brief.title,
        markdown=brief.markdown,
        structured=brief.structured or {},
        model=brief.model,
        created_at=brief.created_at,
        item_count=item_count,
    )


@router.get("/briefs", response_model=list[BriefListItem], summary="简报列表")
async def list_briefs(
    session: SessionDep,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[BriefListItem]:
    item_count = _item_count_subquery()
    stmt = select(Brief, item_count).order_by(Brief.period_start.desc()).limit(limit)
    if kind:
        stmt = stmt.where(Brief.kind == kind)
    rows = (await session.execute(stmt)).all()
    return [
        BriefListItem(
            id=brief.id,
            kind=brief.kind,
            period_start=brief.period_start,
            period_end=brief.period_end,
            title=brief.title,
            model=brief.model,
            created_at=brief.created_at,
            item_count=int(count or 0),
        )
        for brief, count in rows
    ]


@router.get("/briefs/latest", response_model=BriefOut, summary="最新一期简报")
async def latest_brief(
    session: SessionDep,
    kind: Annotated[str, Query(max_length=16)] = "daily",
) -> BriefOut:
    item_count = _item_count_subquery()
    row = (
        await session.execute(
            select(Brief, item_count)
            .where(Brief.kind == kind)
            .order_by(Brief.period_start.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="还没有生成任何简报")
    brief, count = row
    return _to_out(brief, int(count or 0))


@router.get("/briefs/{brief_id}", response_model=BriefOut, summary="简报详情")
async def get_brief(brief_id: int, session: SessionDep) -> BriefOut:
    item_count = _item_count_subquery()
    row = (await session.execute(select(Brief, item_count).where(Brief.id == brief_id))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="简报不存在")
    brief, count = row
    return _to_out(brief, int(count or 0))


async def _load_items(session: AsyncSession, brief_id: int) -> list[SelectedItem]:
    """按 brief_items 还原素材清单，用于重渲染来源列表。"""
    rows = (
        await session.execute(
            select(Document, BriefItem, ClusterMember.cluster_id, Source.name)
            .join(BriefItem, BriefItem.document_id == Document.id)
            .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
            .outerjoin(Source, Source.id == Document.source_id)
            .where(BriefItem.brief_id == brief_id)
            .order_by(BriefItem.rank.asc())
        )
    ).all()
    items: list[SelectedItem] = []
    for document, brief_item, cluster_id, source_name in rows:
        items.append(
            SelectedItem(
                document_id=document.id,
                cluster_id=brief_item.cluster_id or cluster_id,
                title=document.title,
                summary_zh="",
                summary_en="",
                score=0,
                source_name=source_name,
                url=document.url,
                published_at=document.published_at,
                headline_only=False,
            )
        )
    return items


@router.get(
    "/briefs/{brief_id}/markdown",
    summary="按语言重新渲染 Markdown（不调用模型）",
    response_class=Response,
)
async def brief_markdown(
    brief_id: int,
    session: SessionDep,
    language: Annotated[str, Query(pattern="^(zh|en)$")] = "zh",
) -> Response:
    brief = await session.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="简报不存在")
    if not isinstance(brief.structured, dict) or "sections" not in brief.structured:
        # 没有结构化内容的简报（例如"本期无内容"占位）直接回落到已存的 Markdown
        return Response(content=brief.markdown, media_type="text/markdown; charset=utf-8")
    content = BriefContent.model_validate(brief.structured)
    items = await _load_items(session, brief.id)
    markdown = render_markdown(
        content,
        language=language,
        items=items,
        period=(brief.period_start, brief.period_end),
    )
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")
