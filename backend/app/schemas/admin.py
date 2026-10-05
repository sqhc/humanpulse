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


class EntityCandidateSide(BaseModel):
    id: int
    name: str
    mentions: int = 0


class EntityCandidateOut(BaseModel):
    kind: str
    left: EntityCandidateSide
    right: EntityCandidateSide
    shared_documents: int
    jaccard: float


class EntityCandidateListOut(BaseModel):
    candidates: list[EntityCandidateOut] = Field(default_factory=list)
    alias_group_count: int = 0
    alias_problems: list[str] = Field(default_factory=list)
    scanned_pairs: int = 0


class EntityMergeIn(BaseModel):
    """一次确认：把 alias_ids 合并进 canonical_id。"""

    canonical_id: int
    alias_ids: list[int] = Field(default_factory=list)


class EntityAliasApplyIn(BaseModel):
    merges: list[EntityMergeIn]
    # 是否把这次确认写回 YAML（默认只改数据库，避免误改随包文件）
    remember: bool = False


class EntityAliasApplyOut(BaseModel):
    applied_groups: int = 0
    merged: int = 0
    promoted: int = 0
    moved: int = 0
    dropped: int = 0
    missing: int = 0
    remembered: bool = False
    alias_file: str | None = None
    total_groups: int = 0
    problems: list[str] = Field(default_factory=list)


class ProcessRunStats(BaseModel):
    picked: int = 0
    enriched: int = 0
    rejected: int = 0
    failed: int = 0
    skipped_budget: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
