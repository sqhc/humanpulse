"""过旧内容拦截：静态 XML / 归档 feed 不应该混进 Feed。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.pipeline.ingest import is_too_old

NOW = datetime(2026, 9, 27, tzinfo=UTC)


def test_missing_published_at_is_kept() -> None:
    # 没有发布时间的源无法判断新旧，交给别的规则处理（例如源本身被停用）
    assert is_too_old(None, now=NOW, max_age_days=45) is False


def test_recent_item_is_kept() -> None:
    assert is_too_old(NOW - timedelta(days=3), now=NOW, max_age_days=45) is False


def test_boundary_is_kept() -> None:
    assert is_too_old(NOW - timedelta(days=45), now=NOW, max_age_days=45) is False


def test_archive_item_is_dropped() -> None:
    # 新华网那个静态 XML 的条目是 2022 年的，实测就是这样被拦下的
    assert is_too_old(NOW - timedelta(days=1400), now=NOW, max_age_days=45) is True
