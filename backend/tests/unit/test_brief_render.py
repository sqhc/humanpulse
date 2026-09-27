"""渲染：Markdown 由服务端确定性生成（含我们自己拼的来源清单）。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefs.render import render_markdown
from app.briefs.schema import BriefContent
from app.briefs.select import SelectedItem

PERIOD = (datetime(2026, 9, 26, 6, tzinfo=UTC), datetime(2026, 9, 27, 6, tzinfo=UTC))


def content() -> BriefContent:
    return BriefContent(
        title_zh="全球观察日报（2026-09-27）",
        title_en="Global brief (2026-09-27)",
        overview_zh="当天的概述。",
        overview_en="Overview of the day.",
        sections=[
            {
                "key": "conflict",
                "heading_zh": "冲突与安全",
                "heading_en": "Conflict & security",
                "bullets_zh": ["要点一（来源A）"],
                "bullets_en": ["Bullet one (Source A)"],
            },
            {
                "key": "science",
                "heading_zh": "",
                "heading_en": "",
                "bullets_zh": [],
                "bullets_en": [],
            },
        ],
    )


def sample_item() -> SelectedItem:
    return SelectedItem(
        document_id=1,
        cluster_id=3,
        title="边境交火第三日",
        summary_zh="摘要",
        summary_en="summary",
        score=80,
        source_name="Al Jazeera",
        url="https://example.test/a",
        published_at=datetime(2026, 9, 27, tzinfo=UTC),
        headline_only=False,
    )


def test_renders_title_sections_and_sources() -> None:
    markdown = render_markdown(content(), language="zh", items=[sample_item()], period=PERIOD)
    assert markdown.startswith("# 全球观察日报（2026-09-27）")
    assert "## 冲突与安全" in markdown
    assert "- 要点一（来源A）" in markdown
    assert "## 来源清单" in markdown
    assert "[Al Jazeera] 边境交火第三日 — https://example.test/a" in markdown
    assert "1 条素材" in markdown


def test_empty_section_is_skipped_and_default_heading_used() -> None:
    markdown = render_markdown(content(), language="zh", items=[], period=PERIOD)
    assert "科技与科学" not in markdown
    assert "## 来源清单" not in markdown


def test_english_rendering_uses_english_fields() -> None:
    markdown = render_markdown(content(), language="en", items=[sample_item()], period=PERIOD)
    assert markdown.startswith("# Global brief (2026-09-27)")
    assert "## Conflict & security" in markdown
    assert "## Sources" in markdown
    assert "Bullet one (Source A)" in markdown
