"""GDELT DOC 2.0 API 采集器：按源 URL 拉取文章列表。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.collectors.base import RawItem
from app.config import get_settings
from app.models.source import Source

_SEENDATE_FORMAT = "%Y%m%dT%H%M%SZ"


def _parse_seendate(value: Any) -> datetime | None:
    """解析 GDELT 的 seendate（形如 20260101T120000Z）；格式不符则返回 None。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, _SEENDATE_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


class GdeltCollector:
    """GDELT DOC API 采集器。"""

    kind: ClassVar[str] = "gdelt"

    async def fetch(self, source: Source, client: httpx.AsyncClient) -> AsyncIterator[RawItem]:
        settings = get_settings()
        # GDELT 官方建议相邻请求间隔 >=5 秒。本采集器每次只发一个请求，
        # 无从在两个请求之间「间隔」，因此把 sleep 放在请求前节流，避免连续调度时过密。
        if settings.gdelt_throttle_seconds > 0:
            await asyncio.sleep(settings.gdelt_throttle_seconds)

        # setdefault 保证调用方在 source.params 里显式给出的查询参数不被覆盖。
        params: dict[str, Any] = dict(source.params)
        params.setdefault("format", "json")
        params.setdefault("maxrecords", settings.gdelt_max_records)

        response = await client.get(source.url, params=params)
        response.raise_for_status()
        payload = response.json()
        articles = payload.get("articles") if isinstance(payload, dict) else None

        for article in articles or []:
            url = article.get("url")
            title = article.get("title")
            # 缺链接或缺标题的条目既无法回访也无法展示，直接跳过。
            if not url or not title:
                continue
            yield RawItem(
                url=url,
                title=title,
                kind="news",
                summary=article.get("domain"),
                author=None,
                published_at=_parse_seendate(article.get("seendate")),
                language=article.get("language"),
                raw=dict(article),
            )
