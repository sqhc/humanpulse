"""指标采集：提供系统运行时的关键量化指标。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass
class SystemMetrics:
    """系统全局指标计数器。"""

    calls: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)
    latencies: dict[str, list[float]] = field(default_factory=dict)

    _lock = Lock()

    def inc(self, metric: str, tags: str = "default") -> None:
        with self._lock:
            self.calls[f"{metric}:{tags}"] += 1

    def error(self, metric: str, tags: str = "default") -> None:
        with self._lock:
            self.errors[f"{metric}:{tags}"] += 1

    def observe(self, metric: str, value: float, tags: str = "default") -> None:
        with self._lock:
            if metric not in self.latencies:
                self.latencies[metric] = []
            self.latencies[metric].append(value)
            if len(self.latencies[metric]) > 1000:
                self.latencies[metric].pop(0)


metrics = SystemMetrics()


def get_metrics_json() -> dict[str, Any]:
    """导出当前所有指标为 JSON。"""
    return {
        "timestamp": datetime.now().isoformat(),
        "calls": dict(metrics.calls),
        "errors": dict(metrics.errors),
        "latencies": {k: sum(v) / len(v) if v else 0 for k, v in metrics.latencies.items()},
    }
