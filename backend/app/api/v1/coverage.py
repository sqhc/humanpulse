#!/usr/bin/env python3
"""Coverage Calendar API endpoint."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.document import Document
from app.models.source import FetchRun
from app.models.analysis import Analysis

router = APIRouter(prefix="/coverage", tags=["coverage"])

@router.get("/calendar")
async def coverage_calendar(
    days: int = Query(30, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    """获取最近 N 天的采集/富化日历数据。"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    # 查询 fetch_runs 按天聚合（用 items_new 而非 run 次数）
    runs_stmt = select(
        func.date(FetchRun.started_at).label("run_date"),
        func.coalesce(func.sum(FetchRun.items_new), 0).label("collected"),
    ).where(
        func.date(FetchRun.started_at) >= start_date
    ).group_by(func.date(FetchRun.started_at))

    runs_result = await session.execute(runs_stmt)
    runs_by_date = {row.run_date: row.collected for row in runs_result}

    # 查询 documents 按天聚合（仅 enriched，按 Analysis.created_at 聚合）
    docs_stmt = select(
        func.date(Analysis.created_at).label("enriched_date"),
        func.count().label("enriched"),
    ).where(
        Analysis.document_id == Document.id,
        Document.status == "enriched",
        func.date(Analysis.created_at) >= start_date
    ).group_by(func.date(Analysis.created_at))

    docs_result = await session.execute(docs_stmt)
    docs_by_date = {row.enriched_date: row.enriched for row in docs_result}

    # 查询最早有记录的日期（用于前端区分「无底账」vs「断档」）
    earliest_stmt = select(func.min(func.date(FetchRun.started_at))).select_from(FetchRun)
    earliest_date = (await session.execute(earliest_stmt)).scalar()

    # 组装结果
    days = []
    current = start_date
    while current <= date.today():
        collected = runs_by_date.get(current, 0)
        enriched = docs_by_date.get(current, 0)
        has_data = collected > 0

        days.append({
            "date": current.isoformat(),
            "collected": collected,
            "enriched": enriched,
            "has_data": has_data,
        })
        current += timedelta(days=1)

    earliest_date = (await session.execute(
        select(func.min(func.date(FetchRun.started_at))).select_from(FetchRun)
    )).scalar()

    return {
        "days": days,
        "total_collected": sum(runs_by_date.values()),
        "total_enriched": sum(docs_by_date.values()),
        "earliest_ledger_date": earliest_date.isoformat() if earliest_date else None,
        "coverage_rate": sum(1 for d in days if d["has_data"]) / len(days) if days else 0,
    }