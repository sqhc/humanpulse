"""RSS/Atom 采集器：用 feedparser 把订阅源解析成 RawItem 流。"""

from __future__ import annotations

import calendar
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import feedparser  # type: ignore[import-untyped]
import httpx

from app.collectors.base import RawItem
from app.config import get_settings
from app.models.source import Source

# feed 的 description/summary 里常内嵌 HTML，直接入库会污染检索与展示，先剥标签再压缩空白。
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SUMMARY_MAX_LEN = 800


def _clean_summary(raw: str | None) -> str | None:
    """去除 HTML 标签、压缩空白并截断到 800 字；清洗后为空则返回 None。"""
    if not raw:
        return None
    text = _WHITESPACE_RE.sub(" ", _HTML_TAG_RE.sub(" ", raw)).strip()
    if not text:
        return None
    return text[:_SUMMARY_MAX_LEN]


def _parse_published(entry: Any) -> datetime | None:
    """把 feedparser 的 *_parsed 结构时间转成带时区的 UTC datetime。

    feedparser（无类型标注，故此处用 Any）返回的 struct_time 语义是 UTC，
    但本身不带时区，因此用 calendar.timegm 按 UTC 解释，再显式补上 tzinfo。
    """
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


class RssCollector:
    """RSS/Atom 采集器。"""

    kind: ClassVar[str] = "rss"

    async def fetch(self, source: Source, client: httpx.AsyncClient) -> AsyncIterator[RawItem]:
        response = await client.get(source.url)
        response.raise_for_status()
        feed = feedparser.parse(response.content)

        entries = getattr(feed, "entries", None) or []
        # bozo 表示 XML 存在异常；若连条目都解析不出来就无从产出，报错让上层标记失败。
        if not entries and getattr(feed, "bozo", False):
            reason = getattr(feed, "bozo_exception", None)
            raise RuntimeError(f"RSS 解析失败 source={source.name!r}: {reason!r}")

        item_kind = source.params.get("kind", "news")
        feed_title = feed.feed.get("title") if getattr(feed, "feed", None) else None
        max_items = get_settings().rss_max_items_per_feed

        for entry in entries[:max_items]:
            link = entry.get("link")
            title = entry.get("title")
            # 没有链接无法去重回访，没有标题无法展示，一律跳过。
            if not link or not title:
                continue
            yield RawItem(
                url=link,
                title=title,
                kind=item_kind,
                summary=_clean_summary(entry.get("description") or entry.get("summary")),
                author=entry.get("author") or None,
                published_at=_parse_published(entry),
                language=None,
                raw={"feed_title": feed_title},
            )
