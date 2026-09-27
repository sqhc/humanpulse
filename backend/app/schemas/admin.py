"""管理接口的响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRunStats(BaseModel):
    source_id: int
    source_name: str
    status: str
    seen: int = 0
    new: int = 0
    duplicate_url: int = 0
    near_duplicate: int = 0
    invalid: int = 0
    error: str | None = None


class CollectRunStats(BaseModel):
    sources_considered: int = 0
    sources_run: int = 0
    sources_failed: int = 0
    sources_skipped: int = 0
    new_documents: int = 0
    per_source: list[SourceRunStats] = Field(default_factory=list)


class ProcessRunStats(BaseModel):
    picked: int = 0
    enriched: int = 0
    rejected: int = 0
    failed: int = 0
    skipped_budget: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
