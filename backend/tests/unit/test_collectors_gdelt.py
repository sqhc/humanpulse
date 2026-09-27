"""GdeltCollector 单元测试：用 MockTransport 离线返回 fixture 字节。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.gdelt import GdeltCollector
from app.config import get_settings
from app.models.source import Source

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gdelt_sample.json"


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """限速置 0 并清缓存，避免测试真的等待 5 秒。"""
    monkeypatch.setenv("GDELT_THROTTLE_SECONDS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _source(params: dict[str, object] | None = None) -> Source:
    return Source(
        id=2,
        name="样例 GDELT",
        kind="gdelt",
        url="https://api.gdeltproject.org/api/v2/doc/doc",
        params=params or {},
    )


def _client(content: bytes, captured: dict[str, str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.url.params)
        return httpx.Response(200, content=content)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fills_default_params_and_parses_articles(fresh_settings: None) -> None:
    captured: dict[str, str] = {}
    async with _client(FIXTURE.read_bytes(), captured) as client:
        items = [item async for item in GdeltCollector().fetch(_source(), client)]

    # format 与 maxrecords 在未显式给出时被补上默认值。
    assert captured["format"] == "json"
    assert captured["maxrecords"] == str(get_settings().gdelt_max_records)

    # fixture 3 条，其中缺 url 的那条被跳过。
    assert len(items) == 2
    first, second = items

    assert first.url == "https://example.com/one"
    assert first.title == "GDELT One"
    assert first.kind == "news"
    assert first.summary == "example.com"
    assert first.author is None
    assert first.language == "English"
    assert first.raw["domain"] == "example.com"
    assert first.published_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert first.published_at is not None
    assert first.published_at.tzinfo is UTC

    # 非法 seendate 不阻塞条目，只是没有发布时间。
    assert second.url == "https://example.com/two"
    assert second.published_at is None


async def test_explicit_params_are_not_overridden(fresh_settings: None) -> None:
    captured: dict[str, str] = {}
    source = _source({"format": "csv", "maxrecords": 5, "query": "climate"})
    async with _client(FIXTURE.read_bytes(), captured) as client:
        [item async for item in GdeltCollector().fetch(source, client)]

    assert captured["format"] == "csv"
    assert captured["maxrecords"] == "5"
    assert captured["query"] == "climate"
