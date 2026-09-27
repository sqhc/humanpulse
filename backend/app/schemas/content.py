"""面向读取端的响应模型（API 契约的一部分）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    url: str
    canonical_url: str
    title: str
    author: str | None = None
    source_id: int | None = None
    source_name: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    language: str | None = None
    kind: str
    excerpt: str | None = None
    status: str
    rejection_reason: str | None = None
    score: int | None = None
    summary_zh: str | None = None
    summary_en: str | None = None
    tags: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    rationale: str | None = None
    cluster_id: int | None = None
    ai_generated: bool = True


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    next_cursor: int | None = None
    total_returned: int


class DocumentDetailOut(DocumentOut):
    siblings: list[DocumentOut] = Field(
        default_factory=list, description="同一 cluster 的其它报道（不同来源）"
    )


class SourceOut(BaseModel):
    id: int
    name: str
    kind: str
    url: str
    tier: int
    cadence_minutes: int
    enabled: bool
    license_note: str | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    consecutive_failures: int


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    cadence_minutes: int | None = Field(default=None, ge=5, le=1440)
    tier: int | None = Field(default=None, ge=1, le=3)


class ClusterOut(BaseModel):
    id: int
    canonical_document_id: int | None = None
    key_terms: list[str] = Field(default_factory=list)
    doc_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class ClusterDetailOut(ClusterOut):
    documents: list[DocumentOut] = Field(default_factory=list)


class UploadResultOut(BaseModel):
    upload_id: int
    document_id: int
    status: str


class TakedownIn(BaseModel):
    target_url: str = Field(min_length=4, max_length=2048)
    reason: str = Field(min_length=4, max_length=2000)
    requester: str | None = Field(default=None, max_length=200)


class TakedownOut(BaseModel):
    id: int
    status: str


class JobResultOut(BaseModel):
    job: str
    stats: dict[str, object]


class FetchRunOut(BaseModel):
    id: int
    source_id: int
    source_name: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    items_seen: int
    items_new: int
    items_rejected: int
    error: str | None = None


class LlmUsageOut(BaseModel):
    day: str
    provider: str
    model: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
