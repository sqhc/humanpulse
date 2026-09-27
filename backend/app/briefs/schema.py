"""简报内容结构：模型必须按这个结构输出，渲染与前端都基于它。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

PROMPT_VERSION = "v1"

SectionKey = Literal["conflict", "science", "labor", "other"]
SECTION_KEYS: tuple[str, ...] = ("conflict", "science", "labor", "other")

DEFAULT_HEADINGS: dict[str, tuple[str, str]] = {
    "conflict": ("冲突与安全", "Conflict & security"),
    "science": ("科技与科学", "Science & technology"),
    "labor": ("社会运动与劳工", "Social movements & labour"),
    "other": ("其他值得记录", "Also worth noting"),
}


class BriefSection(BaseModel):
    key: SectionKey
    heading_zh: str = Field(default="", max_length=80)
    heading_en: str = Field(default="", max_length=120)
    bullets_zh: list[str] = Field(default_factory=list)
    bullets_en: list[str] = Field(default_factory=list)

    @field_validator("heading_zh", "heading_en")
    @classmethod
    def _fill_heading(cls, value: str, info: object) -> str:
        # 模型偶尔漏标题：用默认标题兜底，避免前端出现空标题分组。
        if value.strip():
            return value.strip()
        key = getattr(info, "data", {}).get("key", "other")
        index = 0 if "zh" in str(getattr(info, "field_name", "")) else 1
        return DEFAULT_HEADINGS.get(str(key), ("其他", "Other"))[index]

    @field_validator("bullets_zh", "bullets_en", mode="before")
    @classmethod
    def _clean_bullets(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = " ".join(str(item).split())
            if text:
                cleaned.append(text[:400])
        return cleaned[:8]


class BriefContent(BaseModel):
    """日报的完整内容（双语）。Markdown 由我们自己渲染，保证可复现。"""

    title_zh: str = Field(default="", max_length=200)
    title_en: str = Field(default="", max_length=200)
    overview_zh: str = Field(default="", max_length=1200)
    overview_en: str = Field(default="", max_length=1200)
    sections: list[BriefSection] = Field(default_factory=list)
    closing_zh: str = Field(default="", max_length=600)
    closing_en: str = Field(default="", max_length=600)

    @field_validator("sections")
    @classmethod
    def _order_sections(cls, value: list[BriefSection]) -> list[BriefSection]:
        order = {key: index for index, key in enumerate(SECTION_KEYS)}
        return sorted(value, key=lambda section: order.get(section.key, len(order)))[:5]

    def is_empty(self) -> bool:
        return not any(section.bullets_zh or section.bullets_en for section in self.sections)
