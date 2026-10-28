"""后台 worker：内置间隔调度（无额外依赖）。

Phase 1 只需要"每 N 分钟跑一次"的语义；需要 cron 表达式或分布式调度时再换 APScheduler。
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog

from app.config import get_settings
from app.db import session_scope
from app.judgement import get_judgement_client
from app.logging import configure_logging
from app.pipeline.alias_worker import run_alias_discovery
from app.pipeline.pulse import monitor_pulse
from app.predictions import resolve_due
from app.workers.jobs import collect_all, run_brief, run_process

log = structlog.get_logger("worker")


async def _loop(
    name: str,
    interval_seconds: float,
    job: Callable[[], Awaitable[None]],
    stop: asyncio.Event,
) -> None:
    """按固定间隔执行作业；异常只记录，不终止循环。"""
    while not stop.is_set():
        try:
            await job()
        except Exception as exc:
            log.error("worker.job_failed", job=name, error=str(exc)[:300])
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async def collect_job() -> None:
        async with session_scope() as session:
            await collect_all(session)

    async def process_job() -> None:
        async with session_scope() as session:
            await run_process(session)

    async def resolve_predictions_job() -> None:
        # 到期核对：判官未配置时直接跳过（不报错，也不假装做了）
        if get_judgement_client() is None:
            return
        async with session_scope() as session:
            report = await resolve_due(session, limit=settings.prediction_resolve_batch)
        if report.checked:
            log.info(
                "predictions.resolved",
                checked=report.checked,
                hit=report.hit,
                missed=report.missed,
                unresolved=report.unresolved,
            )

    async def brief_job() -> None:
        # 到点之后每 15 分钟探一次；生成函数本身幂等（同周期已有就跳过）
        now = datetime.now(UTC)
        if now.hour < settings.brief_hour:
            return
        async with session_scope() as session:
            await run_brief(session, kind="daily")
            if now.weekday() == settings.brief_weekday:
                await run_brief(session, kind="weekly")

    async def alias_discovery_job() -> None:
        # 别名自动发现：仅在启用且判官可用时运行
        if not settings.alias_adjudication_enabled or get_judgement_client() is None:
            return
        async with session_scope() as session:
            await run_alias_discovery(session)

    async def pulse_job() -> None:
        async with session_scope() as session:
            await monitor_pulse(session)

    log.info(
        "worker.start",
        collect_interval_minutes=settings.collect_interval_minutes,
        process_interval_minutes=settings.process_interval_minutes,
        brief_hour=settings.brief_hour,
    )
    await asyncio.gather(
        _loop("collect", settings.collect_interval_minutes * 60, collect_job, stop),
        _loop("process", settings.process_interval_minutes * 60, process_job, stop),
        _loop("brief", 900.0, brief_job, stop),
        _loop(
            "resolve-predictions",
            settings.prediction_resolve_interval_minutes * 60,
            resolve_predictions_job,
            stop,
        ),
        _loop(
            "alias-discovery",
            settings.alias_discovery_interval_minutes * 60,
            alias_discovery_job,
            stop,
        ),
        _loop("pulse", 3600.0, pulse_job, stop),
    )

    log.info("worker.stop")


if __name__ == "__main__":
    asyncio.run(main())
