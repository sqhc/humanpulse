"""日报/周报：选材 → LLM 组稿 → 落库与渲染。"""

from app.briefs.daily import DailyBriefResult, generate_daily_brief
from app.briefs.render import render_markdown
from app.briefs.schema import SECTION_KEYS, BriefContent, BriefSection
from app.briefs.select import SelectedItem, pick_representatives, select_items

__all__ = [
    "SECTION_KEYS",
    "BriefContent",
    "BriefSection",
    "DailyBriefResult",
    "SelectedItem",
    "generate_daily_brief",
    "pick_representatives",
    "render_markdown",
    "select_items",
]
