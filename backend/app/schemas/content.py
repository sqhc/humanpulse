"""面向读取端的响应模型（API 契约的一部分）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EntityRef(BaseModel):
    """文档里抽取的命名实体（供前端关键词高亮用）。"""

    name: str
    kind: str = "org"
    salience: float = 0.0


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
    entities: list[EntityRef] = Field(default_factory=list)
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


class BriefListItem(BaseModel):
    id: int
    kind: str
    period_start: datetime
    period_end: datetime
    title: str
    model: str
    created_at: datetime
    item_count: int = 0


class BriefOut(BaseModel):
    id: int
    kind: str
    period_start: datetime
    period_end: datetime
    language: str
    title: str
    markdown: str
    structured: dict[str, object] = Field(default_factory=dict)
    model: str
    created_at: datetime
    item_count: int = 0


class EntityOut(BaseModel):
    id: int
    name: str
    kind: str
    aliases: list[str] = Field(default_factory=list)
    mention_count: int = 0
    first_seen_at: datetime
    last_seen_at: datetime


class EntityTimelinePoint(BaseModel):
    day: str
    count: int


class EntityMentionOut(BaseModel):
    document_id: int
    title: str
    url: str
    source_name: str | None = None
    published_at: datetime
    score: int | None = None
    cluster_id: int | None = None
    salience: float = 0.0


class EntityDetailOut(EntityOut):
    timeline: list[EntityTimelinePoint] = Field(default_factory=list)
    recent: list[EntityMentionOut] = Field(default_factory=list)


class SearchHitOut(BaseModel):
    document_id: int
    title: str
    url: str
    source_name: str | None = None
    language: str | None = None
    published_at: datetime
    score: int | None = None
    summary_zh: str | None = None
    summary_en: str | None = None
    tags: list[str] = Field(default_factory=list)
    cluster_id: int | None = None
    similarity: float = 0.0


class NoveltyFactorOut(BaseModel):
    """novelty 单个因子的取值与溯源（value=None 表示该因子缺席、未参与加权）。"""

    key: str
    label_zh: str
    label_en: str
    value: float | None = None
    weight: float
    contribution: float = 0.0
    detail_zh: str = ""
    detail_en: str = ""


class NoveltyNeighbourOut(BaseModel):
    """最相似的近邻报道——「为什么这条被判定为相似」的可核对依据。"""

    document_id: int
    title: str
    url: str
    source_name: str | None = None
    similarity: float
    published_at: datetime | None = None


class DocumentNoveltyOut(BaseModel):
    """文档级 novelty（Signal）——确定性工程指标，未经人工标注校准。"""

    document_id: int
    novelty_score: float
    status: str
    factor_breakdown: list[NoveltyFactorOut] = Field(default_factory=list)
    neighbours: list[NoveltyNeighbourOut] = Field(default_factory=list)
    window_days: int
    tau_hours: float
    weights: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    recommendation_zh: str = ""
    recommendation_en: str = ""
    basis_zh: list[str] = Field(default_factory=list)
    basis_en: list[str] = Field(default_factory=list)
    confidence: str = "full"
    calibrated: bool = False
    note_zh: str = ""
    note_en: str = ""


class PredictionOut(BaseModel):
    """登记过的推演（预测）——概率一律标注「未经校准」，不是可发布结论。"""

    id: int
    brief_id: int | None = None
    document_id: int | None = None
    cluster_id: int | None = None
    hop: int = 0
    question_key: str = ""
    statement_zh: str = ""
    statement_en: str = ""
    predicted_probability: float
    confidence: float | None = None
    horizon_days: int = 14
    due_at: str
    status: str
    resolved_at: str | None = None
    resolved_probability: float | None = None
    brier: float | None = None
    provider: str = ""
    model: str = ""


class PredictionListOut(BaseModel):
    total: int
    items: list[PredictionOut]


class ProviderBreakdown(BaseModel):
    resolved: int
    hits: int


class ReliabilityBucket(BaseModel):
    range: str
    count: int
    mean_probability: float
    empirical_rate: float


class CalibrationOut(BaseModel):
    by_status: dict[str, int] = Field(default_factory=dict)
    by_provider: dict[str, ProviderBreakdown] = Field(default_factory=dict)
    provider: str | None = None
    resolved: int = 0
    hits: int = 0
    misses: int = 0
    mixed_providers: list[str] | None = None
    note: str | None = None
    empty_note: str | None = None
    base_rate: float | None = None
    brier: float | None = None
    brier_baseline: float | None = None
    ece: float | None = None
    reliability: list[ReliabilityBucket] | None = None
