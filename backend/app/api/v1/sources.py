"""源管理：列表公开，改动需要管理员 Key。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.db import get_session
from app.models.source import Source
from app.schemas.content import SourceOut, SourceUpdate

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _to_out(source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        name=source.name,
        kind=source.kind,
        url=source.url,
        tier=source.tier,
        cadence_minutes=source.cadence_minutes,
        enabled=source.enabled,
        license_note=source.license_note,
        last_run_at=source.last_run_at,
        last_status=source.last_status,
        consecutive_failures=source.consecutive_failures,
    )


@router.get("/sources", response_model=list[SourceOut], summary="数据源列表")
async def list_sources(session: SessionDep, enabled_only: bool = False) -> list[SourceOut]:
    stmt = select(Source).order_by(Source.tier.asc(), Source.name.asc())
    if enabled_only:
        stmt = stmt.where(Source.enabled.is_(True))
    return [_to_out(s) for s in (await session.execute(stmt)).scalars().all()]


@router.patch("/sources/{source_id}", response_model=SourceOut, summary="启用/停用或调整采集频率")
async def update_source(
    source_id: int,
    payload: SourceUpdate,
    session: SessionDep,
    _admin: AdminDep,
) -> SourceOut:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="源不存在")
    if payload.enabled is not None:
        source.enabled = payload.enabled
        if payload.enabled:
            source.consecutive_failures = 0
    if payload.cadence_minutes is not None:
        source.cadence_minutes = payload.cadence_minutes
    if payload.tier is not None:
        source.tier = payload.tier
    await session.flush()
    return _to_out(source)
