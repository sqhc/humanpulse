"""选材：一个事件（cluster）只留一条代表，避免同一事件刷屏。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefs.select import SelectedItem, pick_representatives


def item(doc_id: int, score: int, cluster_id: int | None = None, day: int = 27) -> SelectedItem:
    return SelectedItem(
        document_id=doc_id,
        cluster_id=cluster_id,
        title=f"标题 {doc_id}",
        summary_zh="中文摘要",
        summary_en="english summary",
        score=score,
        source_name="source",
        url=f"https://example.test/{doc_id}",
        published_at=datetime(2026, 9, day, tzinfo=UTC),
        headline_only=False,
    )


def test_keeps_only_highest_score_per_cluster() -> None:
    picked = pick_representatives(
        [item(1, 40, cluster_id=7), item(2, 90, cluster_id=7), item(3, 60, cluster_id=7)],
        limit=10,
    )
    assert [entry.document_id for entry in picked] == [2]


def test_items_without_cluster_are_kept_separately() -> None:
    picked = pick_representatives([item(1, 40), item(2, 90)], limit=10)
    assert [entry.document_id for entry in picked] == [2, 1]


def test_ranking_is_by_score_then_limit() -> None:
    picked = pick_representatives(
        [item(1, 10, cluster_id=1), item(2, 80, cluster_id=2), item(3, 55, cluster_id=3)],
        limit=2,
    )
    assert [entry.document_id for entry in picked] == [2, 3]


def test_empty_input() -> None:
    assert pick_representatives([], limit=5) == []
