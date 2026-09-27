"""采集器注册表单元测试。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import httpx
import pytest

from app.collectors import get_collector, register, registered_kinds
from app.collectors.base import RawItem
from app.collectors.rss import RssCollector
from app.models.source import Source


class _StubCollector:
    """仅用于覆盖注册行为的最小采集器。"""

    kind: ClassVar[str] = "rss"

    async def fetch(self, source: Source, client: httpx.AsyncClient) -> AsyncIterator[RawItem]:
        return
        yield


def test_builtin_kinds_are_registered() -> None:
    assert {"rss", "gdelt", "manual"} <= set(registered_kinds())
    assert get_collector("rss").kind == "rss"
    assert get_collector("gdelt").kind == "gdelt"
    assert get_collector("manual").kind == "manual"


def test_register_can_override_existing_kind() -> None:
    stub = _StubCollector()
    register(stub)
    assert get_collector("rss") is stub
    # 还原全局注册表，避免影响其他测试。
    register(RssCollector())
    assert isinstance(get_collector("rss"), RssCollector)


def test_unknown_kind_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_collector("does-not-exist")
