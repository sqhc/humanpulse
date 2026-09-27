"""管理接口：手动触发作业、查看采集与用量。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.db import get_session
from app.models.document import FetchRun
from app.models.ops import LlmUsageDay
from app.models.source import Source
from app.schemas.content import FetchRunOut, JobResultOut, LlmUsageOut
from app.workers.jobs import collect_all, run_process

router = APIRouter(prefix="/admin")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/jobs/{job_name}/run", response_model=JobResultOut, summary="手动触发作业（管理员）")
async def run_job(
    job_name: Literal["collect", "process"],
    session: SessionDep,
    _admin: AdminDep,
    force: Annotated[bool, Query(description="忽略 cadence 立即采集")] = False,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> JobResultOut:
    if job_name == "collect":
        stats = (await collect_all(session, force=force)).model_dump()
    else:
        stats = (await run_process(session, limit=limit)).model_dump()
    return JobResultOut(job=job_name, stats=stats)


@router.get("/runs", response_model=list[FetchRunOut], summary="最近的采集批次（管理员）")
async def list_runs(
    session: SessionDep,
    _admin: AdminDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
) -> list[FetchRunOut]:
    rows = (
        await session.execute(
            select(FetchRun, Source.name)
            .outerjoin(Source, Source.id == FetchRun.source_id)
            .order_by(FetchRun.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        FetchRunOut(
            id=run.id,
            source_id=run.source_id,
            source_name=name,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            items_seen=run.items_seen,
            items_new=run.items_new,
            items_rejected=run.items_rejected,
            error=run.error,
        )
        for run, name in rows
    ]


@router.get("/usage", response_model=list[LlmUsageOut], summary="LLM 用量与成本（管理员）")
async def list_usage(
    session: SessionDep,
    _admin: AdminDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> list[LlmUsageOut]:
    since = date.today() - timedelta(days=days)
    rows = (
        (
            await session.execute(
                select(LlmUsageDay)
                .where(LlmUsageDay.day >= since)
                .order_by(LlmUsageDay.day.desc(), LlmUsageDay.model.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        LlmUsageOut(
            day=row.day.isoformat(),
            provider=row.provider,
            model=row.model,
            calls=row.calls,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            cost_usd=float(row.cost_usd or 0),
        )
        for row in rows
    ]
