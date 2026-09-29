"""渲染：把结构化简报变成可复现的 Markdown（不调用模型）。"""

from __future__ import annotations

from datetime import datetime

from app.briefs.schema import DEFAULT_HEADINGS, BriefContent, BriefSection
from app.briefs.select import SelectedItem


def _heading(section: BriefSection, language: str) -> str:
    if language == "en":
        return section.heading_en or DEFAULT_HEADINGS.get(section.key, ("", "Other"))[1]
    return section.heading_zh or DEFAULT_HEADINGS.get(section.key, ("Other", ""))[0]


def render_markdown(
    content: BriefContent,
    *,
    language: str = "zh",
    items: list[SelectedItem] | None = None,
    period: tuple[datetime, datetime] | None = None,
) -> str:
    """输出 Markdown；来源清单由我们按素材生成，避免模型编造链接。"""
    lines: list[str] = []
    title = content.title_en if language == "en" else content.title_zh
    overview = content.overview_en if language == "en" else content.overview_zh
    closing = content.closing_en if language == "en" else content.closing_zh
    fallback_title = "humanpulse brief" if language == "en" else "humanpulse 简报"

    lines.append("# " + (title or fallback_title))
    if period is not None:
        start, end = period
        lines.append("")
        start_text = start.strftime("%Y-%m-%d %H:%M")
        end_text = end.strftime("%Y-%m-%d %H:%M")
        lines.append(f"_{start_text} → {end_text} UTC（{len(items or [])} 条素材）_")
    if overview:
        lines.append("")
        lines.append(overview)

    trends = content.trends_en if language == "en" else content.trends_zh
    if trends:
        lines.append("")
        lines.append("## Trends" if language == "en" else "## 本周趋势")
        lines.extend(f"- {item}" for item in trends)

    for section in content.sections:
        bullets = section.bullets_en if language == "en" else section.bullets_zh
        if not bullets:
            continue
        lines.append("")
        lines.append("## " + _heading(section, language))
        lines.extend("- " + bullet for bullet in bullets)

    if closing:
        lines.append("")
        lines.append(closing)

    if items:
        lines.append("")
        lines.append("## Sources" if language == "en" else "## 来源清单")
        for item in items:
            source = item.source_name or "unknown"
            lines.append(f"- [{source}] {item.title} — {item.url}")

    return "\n".join(lines).strip() + "\n"
