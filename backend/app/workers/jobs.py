"""后台作业：采集（含熔断）与处理。管理接口与 worker 共用同一套实现。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import get_collector
from app.config import get_settings
from app.models.document import FetchRun
from app.models.source import Source
from app.pipeline.ingest import ingest_items
from app.pipeline.process import process_pending
from app.schemas.admin import CollectRunStats, ProcessRunStats, SourceRunStats

log = structlog.get_logger("worker.jobs")

# 连续失败达到该次数即自动停用该源（避免持续烧配额与被封）
CIRCUIT_BREAKER_THRESHOLD = 3


def http_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.collector_timeout_seconds),
        headers={"User-Agent": settings.collector_user_agent},
        proxy=settings.http_proxy or None,
        follow_redirects=True,
    )


async def collect_all(
    session: AsyncSession,
    *,
    force: bool = False,
    kinds: list[str] | None = None,
) -> CollectRunStats:
    """按 cadence 采集到期的启用源；单个源失败不影响其它源。"""
    now = datetime.now(UTC)
    stats = CollectRunStats()

    stmt = (
        select(Source)
        .where(Source.enabled.is_(True))
        .where(Source.kind != "manual")
        .order_by(Source.tier.asc(), Source.id.asc())
    )
    if kinds:
        stmt = stmt.where(Source.kind.in_(kinds))
    sources = list((await session.execute(stmt)).scalars().all())
    stats.sources_considered = len(sources)

    if not sources:
        return stats

    async with http_client() as client:
        for source in sources:
            due_at = None
            if source.last_run_at is not None:
                due_at = source.last_run_at + timedelta(minutes=source.cadence_minutes)
            if not force and due_at is not None and due_at > now:
                stats.sources_skipped += 1
                continue

            run = FetchRun(source_id=source.id, started_at=datetime.now(UTC), status="running")
            session.add(run)
            await session.flush()

            per_source = SourceRunStats(
                source_id=source.id, source_name=source.name, status="success"
            )
            try:
                collector = get_collector(source.kind)
                items = [item async for item in collector.fetch(source, client)]
                result = await ingest_items(
                    session, source=source, fetch_run_id=run.id, items=items
                )
                run.status = "success"
                run.items_seen = result.seen
                run.items_new = result.new
                run.items_rejected = result.duplicate_url + result.near_duplicate
                source.last_status = "ok"
                source.consecutive_failures = 0
                stats.sources_run += 1
                stats.new_documents += result.new
                per_source.seen = result.seen
                per_source.new = result.new
                per_source.duplicate_url = result.duplicate_url
                per_source.near_duplicate = result.near_duplicate
                per_source.invalid = result.invalid
            except Exception as exc:
                run.status = "failed"
                run.error = str(exc)[:500]
                source.last_status = "error"
                source.consecutive_failures = (source.consecutive_failures or 0) + 1
                if source.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    source.enabled = False
                    log.warning("source.circuit_open", source=source.name)
                stats.sources_failed += 1
                per_source.status = "failed"
                per_source.error = str(exc)[:300]
                log.warning("collect.failed", source=source.name, error=str(exc)[:200])
            finally:
                run.finished_at = datetime.now(UTC)
                source.last_run_at = datetime.now(UTC)
                stats.per_source.append(per_source)
                await session.commit()

    log.info("collect.done", **stats.model_dump(exclude={"per_source"}))
    return stats


async def run_process(session: AsyncSession, *, limit: int | None = None) -> ProcessRunStats:
    settings = get_settings()
    result = await process_pending(session, limit=limit or settings.process_batch_size)
    await session.commit()
    return ProcessRunStats(**result.as_dict())
