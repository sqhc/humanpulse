"""SSE 实时流：新富化文档推给前端，取代轮询。

实现方式是**服务端短轮询 + SSE 推送**（每 3 秒查一次 documents），而不是 Postgres LISTEN/NOTIFY：
- 前者不需要数据库触发器/迁移，测试与本地开发都能直接跑；
- 延迟上限 = 轮询间隔（3 秒），对本场景足够；
- 多副本时每个副本各自轮询，客户端只连一个副本，语义正确。
数据量上来后可以换成 LISTEN/NOTIFY（在 documents 上加触发器 + 独立连接），本模块的对外协议不变。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.db import session_scope
from app.models.analysis import Analysis, ClusterMember
from app.models.document import Document
from app.models.source import Source

log = structlog.get_logger("api.stream")

router = APIRouter()

POLL_SECONDS = 3.0
HEARTBEAT_SECONDS = 15.0
BATCH_LIMIT = 20


def sse_frame(event: str, data: dict[str, Any]) -> str:
    """SSE 帧格式：event + data + 空行结尾（纯函数，便于单测）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def document_payload(
    document: Document,
    analysis: Analysis | None,
    cluster_id: int | None,
    source_name: str | None,
) -> dict[str, Any]:
    return {
        "id": document.id,
        "title": document.title,
        "url": document.url,
        "source_name": source_name,
        "language": document.language,
        "kind": document.kind,
        "published_at": document.published_at.isoformat() if document.published_at else None,
        "fetched_at": document.fetched_at.isoformat() if document.fetched_at else None,
        "score": analysis.score if analysis else None,
        "summary_zh": analysis.summary_zh if analysis else None,
        "summary_en": analysis.summary_en if analysis else None,
        "tags": list(analysis.tags) if analysis else [],
        "cluster_id": cluster_id,
    }


def latest_analysis_id_subquery() -> Any:
    return (
        select(func.max(Analysis.id))
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )


async def latest_enriched_id() -> int:
    async with session_scope() as session:
        stmt = select(func.coalesce(func.max(Document.id), 0)).where(Document.status == "enriched")
        return int((await session.execute(stmt)).scalar_one() or 0)


async def fetch_since(last_id: int) -> list[dict[str, Any]]:
    """取 id 大于 last_id 的已富化文档（含最新一次分析）。"""
    async with session_scope() as session:
        latest = latest_analysis_id_subquery()
        rows = (
            await session.execute(
                select(Document, Analysis, ClusterMember.cluster_id, Source.name)
                .outerjoin(Analysis, Analysis.id == latest)
                .outerjoin(ClusterMember, ClusterMember.document_id == Document.id)
                .outerjoin(Source, Source.id == Document.source_id)
                .where(Document.status == "enriched")
                .where(Document.id > last_id)
                .order_by(Document.id.asc())
                .limit(BATCH_LIMIT)
            )
        ).all()
        return [
            document_payload(document, analysis, cluster_id, source_name)
            for document, analysis, cluster_id, source_name in rows
        ]


async def event_stream(request: Request, since: int | None = None) -> AsyncIterator[str]:
    """生成 SSE 事件：ready → document* → ping（空闲心跳）。"""
    cursor = since if since is not None else await latest_enriched_id()
    yield sse_frame("ready", {"cursor": cursor, "poll_seconds": POLL_SECONDS})

    idle = 0.0
    while True:
        if await request.is_disconnected():
            break
        await asyncio.sleep(POLL_SECONDS)
        idle += POLL_SECONDS
        try:
            payloads = await fetch_since(cursor)
        except Exception as exc:
            log.warning("stream.fetch_failed", error=str(exc)[:200])
            yield sse_frame("error", {"message": "查询失败，稍后重试"})
            continue
        if payloads:
            idle = 0.0
            for payload in payloads:
                cursor = max(cursor, int(payload["id"]))
                yield sse_frame("document", payload)
        elif idle >= HEARTBEAT_SECONDS:
            idle = 0.0
            yield ": ping\n\n"


@router.get("/stream", summary="Feed 实时事件流（SSE）")
async def stream(
    request: Request,
    since: Annotated[int | None, Query(ge=0, description="从哪个 document id 之后开始推送")] = None,
) -> StreamingResponse:
    return StreamingResponse(
        event_stream(request, since),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "x-accel-buffering": "no",
        },
    )
