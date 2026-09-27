"""GDELT 429：退避重试一次后应当成功，而不是让整源失败。"""

from __future__ import annotations

from typing import Any

import httpx

from app.collectors.gdelt import GdeltCollector
from app.config import get_settings
from app.models.source import Source


async def test_retry_on_429_then_success(monkeypatch: Any) -> None:
    monkeypatch.setenv("GDELT_THROTTLE_SECONDS", "0")
    get_settings.cache_clear()

    import app.collectors.gdelt as gdelt_module

    monkeypatch.setattr(gdelt_module, "_BACKOFF_SECONDS", 0.01)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "url": "https://example.test/1",
                        "title": "Ceasefire talks resume",
                        "seendate": "20260927T130000Z",
                        "domain": "example.test",
                        "language": "English",
                    }
                ]
            },
        )

    source = Source(
        id=1,
        name="gdelt-test",
        kind="gdelt",
        url="https://api.gdeltproject.org/api/v2/doc/doc",
        params={"mode": "artlist"},
        tier=1,
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        items = [item async for item in GdeltCollector().fetch(source, client)]

    get_settings.cache_clear()

    assert calls["n"] == 2
    assert len(items) == 1
    assert items[0].url == "https://example.test/1"
    assert items[0].published_at is not None
