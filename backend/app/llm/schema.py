"""LLM 输出的严格结构（Pydantic 校验 + 规范化）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

PROMPT_VERSION = "v1"
MAX_TAGS = 8
MAX_REGIONS = 6
MAX_ENTITIES = 15

EntityKind = Literal["person", "org", "place", "event"]


class EntityOut(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: EntityKind = "org"
    salience: float = Field(default=0.0, ge=0.0, le=1.0)


class AnalysisOut(BaseModel):
    """与 llm/prompts/*.md 中约定的 JSON 结构一一对应。"""

    relevant: bool
    score: int = Field(ge=0, le=100)
    summary_zh: str = Field(default="", max_length=1200)
    summary_en: str = Field(default="", max_length=1200)
    tags: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=600)
    entities: list[EntityOut] = Field(default_factory=list)

    @field_validator("tags", "regions", mode="before")
    @classmethod
    def _clean_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",")]
        if not isinstance(value, list):
            return []
        seen: list[str] = []
        for item in value:
            text = str(item).strip().lower()
            if not text or text in seen:
                continue
            seen.append(text[:40])
        return seen

    @field_validator("entities", mode="before")
    @classmethod
    def _clean_entities(cls, value: object) -> list[object]:
        if value is None:
            return []
        if isinstance(value, str):
            return [{"name": value, "kind": "org", "salience": 0.0}]
        if not isinstance(value, list):
            return []
        cleaned: list[object] = []
        for item in value:
            if isinstance(item, str):
                cleaned.append({"name": item, "kind": "org", "salience": 0.0})
            elif isinstance(item, dict):
                cleaned.append(item)
        return cleaned

    @field_validator("tags")
    @classmethod
    def _limit_tags(cls, value: list[str]) -> list[str]:
        return value[:MAX_TAGS]

    @field_validator("regions")
    @classmethod
    def _limit_regions(cls, value: list[str]) -> list[str]:
        return value[:MAX_REGIONS]

    @field_validator("entities")
    @classmethod
    def _limit_entities(cls, value: list[EntityOut]) -> list[EntityOut]:
        return sorted(value, key=lambda e: e.salience, reverse=True)[:MAX_ENTITIES]
