"""plan_document：决定这条文档走哪个提示词、要不要拒绝。"""

from __future__ import annotations

from app.models.document import Document
from app.pipeline.process import HEADLINE_TAG, plan_document


def make_document(doc_id: int, title: str, excerpt: str | None) -> Document:
    return Document(
        id=doc_id,
        title=title,
        excerpt=excerpt,
        url=f"https://example.test/{doc_id}",
        canonical_url=f"https://example.test/{doc_id}",
        kind="news",
        status="pending",
    )


def test_long_body_uses_source_kind() -> None:
    doc = make_document(1, "边境冲突进入第三日", "a" * 120)
    item = plan_document(doc)
    assert item is not None
    assert item.prompt_kind == "news"
    assert item.headline_only is False
    assert "a" * 120 in item.text


def test_domain_only_body_falls_back_to_headline_mode() -> None:
    doc = make_document(2, "PM Modi recalls 2016 surgical strikes on Pakistan", "aninews.in")
    item = plan_document(doc)
    assert item is not None
    assert item.prompt_kind == "headline"
    assert item.headline_only is True
    assert "[仅标题可用]" in item.text
    assert HEADLINE_TAG == "headline-only"


def test_missing_excerpt_uses_headline_mode() -> None:
    doc = make_document(3, "A headline that is long enough to analyse", None)
    item = plan_document(doc)
    assert item is not None
    assert item.headline_only is True
    assert "unknown" in item.text


def test_too_short_title_is_skipped() -> None:
    doc = make_document(4, "短标题", "trend.az")
    assert plan_document(doc) is None
