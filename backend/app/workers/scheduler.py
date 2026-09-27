"""后台 worker 入口。

Phase 0 只维持进程存活（无任务注册）；Phase 1 起接入 APScheduler：
采集、处理、日报/周报分别注册为独立任务。
"""

from __future__ import annotations

import asyncio
import signal

import structlog

from app.config import get_settings
from app.logging import configure_logging

IDLE_SECONDS = 60.0


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger("worker")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info("worker.start", jobs=[])
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=IDLE_SECONDS)
        except TimeoutError:
            log.debug("worker.idle")
    log.info("worker.stop")


if __name__ == "__main__":
    asyncio.run(main())
