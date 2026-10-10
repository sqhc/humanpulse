"""时间窗锚点：离线重建必须用"当前文档的时间"，不能用墙钟。

背景（真实 bug）：reembed 离线重跑时，find_nearest 的窗口锚在墙钟 now 上，
如果最近一次采集是几天前，窗口内一篇文档都没有 → 全部各自成簇，
看起来像"语义向量质量差"，实际上是时间窗失效。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.pipeline.dedup import is_duplicate, is_recent, window_anchor


def test_window_anchor_prefers_document_time() -> None:
    """锚点用文档自身时间，所以离线重放老数据也能聚起来。"""
    moment = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    anchor = window_anchor(published_at=moment, fetched_at=None)
    assert anchor == moment


def test_window_anchor_falls_back_to_fetched_at() -> None:
    fetched = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    assert window_anchor(published_at=None, fetched_at=fetched) == fetched


def test_window_anchor_accepts_naive_datetime() -> None:
    naive = datetime(2026, 9, 27, 12, 0)
    anchor = window_anchor(published_at=naive, fetched_at=None)
    assert anchor is not None and anchor.tzinfo is not None


def test_window_anchor_uses_reference_when_no_document_time() -> None:
    """两者都缺时才退回参考时间（实时采集场景下等价于 now）。"""
    reference = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    assert window_anchor(published_at=None, fetched_at=None, reference=reference) == reference


def test_window_anchor_rejects_absurdly_old_fetched_at() -> None:
    """fetched_at 明显早于 published_at（数据脏）时，信任 published_at。"""
    published = datetime(2026, 9, 27, tzinfo=UTC)
    fetched = datetime(2020, 1, 1, tzinfo=UTC)
    assert window_anchor(published_at=published, fetched_at=fetched) == published


def test_hot_detection_relative_to_document_time() -> None:
    """is_hot 也必须相对文档时间判断，否则离线重建会把所有文档都当冷数据。"""
    moment = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    assert is_recent(moment, reference=moment + timedelta(hours=1), window_hours=24) is True
    assert is_recent(moment, reference=moment + timedelta(hours=48), window_hours=24) is False


def test_is_duplicate_thresholds_unchanged() -> None:
    assert is_duplicate(0.9, is_hot=False, threshold=0.85, hot_threshold=0.80) is True
    assert is_duplicate(0.82, is_hot=False, threshold=0.85, hot_threshold=0.80) is False
    assert is_duplicate(0.82, is_hot=True, threshold=0.85, hot_threshold=0.80) is True
