"""素材清单文本：仅标题条目必须显式标注，避免模型当成有正文。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefs.daily import format_items
from app.briefs.select import SelectedItem


def make_item(headline_only: bool) -> SelectedItem:
    return SelectedItem(
        document_id=1,
        cluster_id=None,
        title="Ceasefire talks resume",
        summary_zh="中文摘要",
        summary_en="english summary",
        score=70,
        source_name="DW Top Stories",
        url="https://example.test/a",
        published_at=datetime(2026, 9, 27, tzinfo=UTC),
        headline_only=headline_only,
    )


def test_headline_only_item_is_labelled() -> None:
    text = format_items([make_item(headline_only=True)])
    assert "（仅据标题）" in text
    assert "DW Top Stories" in text
    assert "https://example.test/a" in text


def test_normal_item_has_no_headline_label() -> None:
    text = format_items([make_item(headline_only=False)])
    assert "（仅据标题）" not in text
