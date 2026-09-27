"""采集器注册入口。

导入 app.collectors 即完成 rss / gdelt / manual 三个内置采集器的注册，
之后 get_collector("rss") 之类的查询即可用。
"""

from __future__ import annotations

from app.collectors.base import (
    Collector,
    RawItem,
    get_collector,
    register,
    registered_kinds,
)
from app.collectors.gdelt import GdeltCollector
from app.collectors.manual import ManualCollector
from app.collectors.rss import RssCollector

register(RssCollector())
register(GdeltCollector())
register(ManualCollector())

__all__ = [
    "Collector",
    "RawItem",
    "get_collector",
    "register",
    "registered_kinds",
]
