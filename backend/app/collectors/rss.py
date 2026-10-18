"""RSS/Atom 采集器：用 feedparser 把订阅源解析成 RawItem 流。"""

from __future__ import annotations

import calendar
import random
import re
import time
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
        """获取 RSS/Atom 订阅源数据，支持指数退避重试。

        Args:
            source: 源配置信息
            client: HTTP 客户端

        Yields:
            RawItem: 解析出的新闻项

        Raises:
            RuntimeError: 经过重试后仍无法解析 RSS 或请求失败
        """
        max_retries = 3
        base_delay = 0.5  # 秒
        max_delay = 10.0  # 秒

        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                # 指数退避重试逻辑
                if attempt > 0:
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0.9, 1.1)  # 添加随机抖动避免同步
                    time.sleep(delay * jitter)

                response = await client.get(source.url, timeout=30.0)
                response.raise_for_status()

                # 解析 RSS/Atom  feed
                feed = feedparser.parse(response.content)

                # 检查 bozo 标志 - 可能表示 XML 解析警告，但不一定致命
                if hasattr(feed, "bozo") and feed.bozo and getattr(feed, "bozo_exception", None):
                    # 记录解析警告但继续处理 - 这可能是暂时的网络/编码问题
                    pass

                entries = getattr(feed, "entries", None) or []

                # 如果完全没有条目（可能真的失败了）才抛出异常
                if not entries:
                    reason = getattr(feed, "bozo_exception", None)
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"RSS 解析失败 source={source.name!r}: {reason!r}")
                    else:
                        # 继续重试
                        continue

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
                # 成功获取到数据，退出重试循环
                return

            except (
                httpx.HTTPStatusError,
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ProtocolError,
            ) as e:
                last_error = e
                if attempt == max_retries - 1:
                    # 所有重试都失败了，抛出异常
                    raise RuntimeError(
                        f"RSS 获取失败 source={source.name!r} URL={source.url!r} "
                        f"after {max_retries} attempts: {e!s}"
                    ) from e
                # 继续重试
                continue

            except Exception as e:
                # 其他异常（如解析错误）也重试
                last_error = e
                if attempt == max_retries - 1:
                    # 所有重试都失败了，抛出异常
                    raise RuntimeError(
                        f"RSS 解析异常 source={source.name!r} URL={source.url!r} "
                        f"after {max_retries} attempts: {e!s}"
                    ) from e
                # 继续重试
                continue

        # 如果循环正常结束但没有 yield 数据（理论上不会发生）
        if last_error:
            raise RuntimeError(
                f"RSS 获取异常 source={source.name!r} URL={source.url!r}: {last_error!s}"
            )
