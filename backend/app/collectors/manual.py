"""手动来源占位采集器。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import httpx

from app.collectors.base import RawItem
from app.models.source import Source


class ManualCollector:
    """手动上传来源。

    手动上传不经过采集器：内容通过 POST /api/v1/uploads 提交，
    由 pipeline 直接构造 RawItem。这里注册一个 manual 采集器，
    只是为了让 source.kind 在注册表里有对应项，因此 fetch 虽是 async
    生成器形态，却不会产出任何条目。
    """

    kind: ClassVar[str] = "manual"

    async def fetch(self, source: Source, client: httpx.AsyncClient) -> AsyncIterator[RawItem]:
        """不产出条目；保留 async 生成器形态以匹配 Collector 契约。"""
        return
        yield
