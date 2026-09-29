"""日报/周报：选材 → LLM 组稿 → 落库与渲染。"""

from app.briefs.daily import DailyBriefResult, generate_daily_brief
from app.briefs.render import render_markdown
from app.briefs.schema import SECTION_KEYS, BriefContent, BriefSection
from app.briefs.select import SelectedItem, pick_representatives, select_items
from app.briefs.weekly import (
    WeeklyBriefResult,
    WeeklyTrends,
    compute_trends,
    format_trends,
    generate_weekly_brief,
    rank_tag_deltas,
)

__all__ = [
    "SECTION_KEYS",
    "BriefContent",
    "BriefSection",
    "DailyBriefResult",
    "SelectedItem",
    "WeeklyBriefResult",
    "WeeklyTrends",
    "compute_trends",
    "format_trends",
    "generate_daily_brief",
    "generate_weekly_brief",
    "pick_representatives",
    "rank_tag_deltas",
    "render_markdown",
    "select_items",
]
