"""Coverage Calendar API：采集底账日历（Signal 同层的诚实呈现，纯事实不做推断）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.analysis import Analysis
from app.models.document import Document, FetchRun
from app.schemas.content import CoverageCalendarOut, CoverageDayOut

router = APIRouter(prefix="/coverage", tags=["coverage"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/calendar",
    response_model=CoverageCalendarOut,
    summary="采集底账日历（采集量 + 富化量，按天，区分断档/空转/无底账）",
)
async def coverage_calendar(
    session: SessionDep,
    days: int = Query(30, ge=1, le=90),
) -> CoverageCalendarOut:
    """获取最近 N 天的采集/富化日历数据。

    口径说明（诚实层约束）：
    - collected 按当天 FetchRun.items_new 求和（采到的新条数，不是跑了几批）
    - enriched 按当天 Analysis.created_at 聚合（当天实际富化完成的量，与发布日期无关）
    - earliest_ledger_date 之前的日子是「无底账记录」，不是「断档」——前端要区分这两种状态
    """
    # 聚合统一用 UTC 日期（与 DB 存储时区一致）；用宿主本地时区会导致
    # 美东时段跨零点的记录被切到错误的日历格（实测有日期错窗问题）。
    today_utc = datetime.now(UTC).date()
    start_date = today_utc - timedelta(days=days - 1)

    runs_stmt = (
        select(
            func.date(FetchRun.started_at).label("run_date"),
            func.coalesce(func.sum(FetchRun.items_new), 0).label("collected"),
        )
        .where(func.date(FetchRun.started_at) >= start_date)
        .group_by(func.date(FetchRun.started_at))
    )
    runs_by_date = {row.run_date: row.collected for row in (await session.execute(runs_stmt)).all()}

    docs_stmt = (
        select(
            func.date(Analysis.created_at).label("enriched_date"),
            func.count().label("enriched"),
        )
        .where(
            Analysis.document_id == Document.id,
            Document.status == "enriched",
            func.date(Analysis.created_at) >= start_date,
        )
        .group_by(func.date(Analysis.created_at))
    )
    docs_by_date = {
        row.enriched_date: row.enriched for row in (await session.execute(docs_stmt)).all()
    }

    earliest_stmt = select(func.min(func.date(FetchRun.started_at))).select_from(FetchRun)
    earliest_date = (await session.execute(earliest_stmt)).scalar()

    out_days: list[CoverageDayOut] = []
    current = start_date
    while current <= today_utc:
        collected = runs_by_date.get(current, 0)
        enriched = docs_by_date.get(current, 0)
        out_days.append(
            CoverageDayOut(
                date=current.isoformat(),
                collected=collected,
                enriched=enriched,
                has_data=collected > 0,
            )
        )
        current += timedelta(days=1)

    return CoverageCalendarOut(
        days=out_days,
        total_collected=sum(day.collected for day in out_days),
        total_enriched=sum(day.enriched for day in out_days),
        earliest_ledger_date=earliest_date.isoformat() if earliest_date else None,
        coverage_rate=(
            sum(1 for day in out_days if day.has_data) / len(out_days) if out_days else 0.0
        ),
    )
