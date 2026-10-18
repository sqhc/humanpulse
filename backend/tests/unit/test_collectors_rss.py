"""RssCollector 单元测试：用 MockTransport 离线返回 fixture 字节。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.base import RawItem
from app.collectors.rss import RssCollector
from app.config import get_settings
from app.models.source import Source

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rss_sample.xml"


@pytest.fixture
def fresh_settings() -> Iterator[None]:
    """清空 get_settings 缓存，避免环境变量 monkeypatch 被 lru_cache 串台。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _source(params: dict[str, object] | None = None) -> Source:
    return Source(
        id=1,
        name="样例 RSS",
        kind="rss",
        url="https://example.com/feed.xml",
        params=params or {},
    )


def _client(content: bytes) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _collect(collector: RssCollector, source: Source, content: bytes) -> list[RawItem]:
    async with _client(content) as client:
        return [item async for item in collector.fetch(source, client)]


async def test_parses_entries_and_skips_missing_link(fresh_settings: None) -> None:
    items = await _collect(RssCollector(), _source(), FIXTURE.read_bytes())

    # fixture 共 3 条，其中缺 link 的那条应被跳过。
    assert len(items) == 2
    first, third = items

    assert first.url == "https://example.com/a"
    assert first.title == "First & Foremost"
    assert first.kind == "news"
    assert first.author == "alice@example.com (Alice)"
    assert first.language is None
    assert first.raw == {"feed_title": "Sample Feed"}

    # description 里的 HTML 标签已被剥离，只留纯文本。
    assert first.summary is not None
    assert "<" not in first.summary and ">" not in first.summary
    assert "Hello world" in first.summary
    assert "First" not in first.summary

    # published_parsed 转成 aware UTC。
    assert first.published_at == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    assert first.published_at is not None
    assert first.published_at.tzinfo is UTC

    assert third.url == "https://example.com/c"
    assert third.title == "Third Entry"
    assert third.published_at == datetime(2024, 1, 3, 8, 30, tzinfo=UTC)
    assert third.summary is not None and "Plain italic text" in third.summary


async def test_source_params_kind_override(fresh_settings: None) -> None:
    items = await _collect(RssCollector(), _source({"kind": "policy"}), FIXTURE.read_bytes())
    assert items and all(item.kind == "policy" for item in items)


async def test_max_items_limit(fresh_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RSS_MAX_ITEMS_PER_FEED", "1")
    get_settings.cache_clear()

    items = await _collect(RssCollector(), _source(), FIXTURE.read_bytes())
    assert len(items) == 1
    assert items[0].url == "https://example.com/a"


async def test_bozo_without_entries_raises(fresh_settings: None) -> None:
    collector = RssCollector()
    with pytest.raises(RuntimeError, match="RSS 解析失败"):
        async with _client(b"not xml at all <<<") as client:
            async for _ in collector.fetch(_source(), client):
                pass


async def test_rss_collector_retry_http_error(
    fresh_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """测试 HTTP 错误时 RSS 采集器的重试逻辑。"""
    import httpx

    from app.collectors.rss import RssCollector
    from app.models.source import Source

    attempt_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        # 第一次失败，第二次成功
        if attempt_count == 1:
            return httpx.Response(404, request=request)
        else:
            # 返回一个有效的 RSS feed
            return httpx.Response(
                200,
                content=b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>Test feed</description>
    <item>
      <title>Test Entry</title>
      <link>https://example.com/test</link>
      <description>Test description</description>
    </item>
  </channel>
</rss>""",
            )

    collector = RssCollector()
    source = Source(
        id=1, name="Test RSS", kind="rss", url="https://example.com/feed.xml", params={}
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = [item async for item in collector.fetch(source, client)]

    # 应该成功获取到一个条目
    assert len(items) == 1
    assert items[0].title == "Test Entry"
    # 应该进行了重试（两次请求：第一次失败，第二次成功）
    assert attempt_count == 2


async def test_rss_retry_parse_error(fresh_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """测试解析错误时 RSS 采集器的重试逻辑。"""
    import httpx

    from app.collectors.rss import RssCollector
    from app.models.source import Source

    attempt_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        # 第一次返回无效 XML，第二次返回有效内容
        if attempt_count == 1:
            return httpx.Response(200, content=b"invalid xml <<<")
        else:
            # 返回一个有效的 RSS feed
            return httpx.Response(
                200,
                content=b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>Test feed</description>
    <item>
      <title>Test Entry</title>
      <link>https://example.com/test</link>
      <description>Test description</description>
    </item>
  </channel>
</rss>""",
            )

    collector = RssCollector()
    source = Source(
        id=1, name="Test RSS", kind="rss", url="https://example.com/feed.xml", params={}
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = [item async for item in collector.fetch(source, client)]

    # 应该成功获取到一个条目
    assert len(items) == 1
    assert items[0].title == "Test Entry"
    # 应该进行了重试（两次请求：第一次解析错误，第二次成功）
    assert attempt_count == 2


async def test_rss_max_retries(fresh_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """测试达到最大重试次数后抛出异常。"""
    import httpx

    from app.collectors.rss import RssCollector
    from app.models.source import Source

    attempt_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        # 总是返回无效 XML，导致解析错误
        return httpx.Response(200, content=b"invalid xml <<<")

    collector = RssCollector()
    source = Source(
        id=1, name="Test RSS", kind="rss", url="https://example.com/feed.xml", params={}
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="RSS 解析异常"):
            async for _ in collector.fetch(source, client):
                pass

    # 应该进行了最大重试次数（3次）
    assert attempt_count == 3
