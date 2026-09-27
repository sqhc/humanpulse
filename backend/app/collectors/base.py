"""采集器契约。

每个采集器只负责"把一个源变成 RawItem 流"，去重、评分、入库都不在这里做。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Protocol, runtime_checkable

import httpx

from app.models.source import Source


@dataclass(slots=True)
class RawItem:
    """采集器输出的原始条目（尚未归一化）。"""

    url: str
    title: str
    kind: str = "news"
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Collector(Protocol):
    kind: ClassVar[str]

    def fetch(self, source: Source, client: httpx.AsyncClient) -> AsyncIterator[RawItem]:
        """产出该源的原始条目；调用方负责限速与错误隔离。"""
        ...


_REGISTRY: dict[str, Collector] = {}


def register(collector: Collector) -> Collector:
    _REGISTRY[collector.kind] = collector
    return collector


def get_collector(kind: str) -> Collector:
    if kind not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "(空)"
        raise KeyError(f"未知采集器 kind={kind!r}，已注册：{known}")
    return _REGISTRY[kind]


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)
