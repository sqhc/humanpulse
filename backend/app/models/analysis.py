"""AI 分析结果、向量与聚类。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Analysis(Base, TimestampMixin):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    prompt_version: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    relevant: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    score: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    summary_zh: Mapped[str] = mapped_column(Text, default="")
    summary_en: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(default=list)
    regions: Mapped[list[str]] = mapped_column(default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    # 实体暂存为 JSONB（结构同 llm.schema.EntityOut）；
    # 需要实体时间线时（Phase 3）再拆出 entities / entity_mentions 表
    entities: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal(0), server_default="0"
    )


class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        Index(
            "ix_embeddings_vec_hnsw",
            "vec",
            postgresql_using="hnsw",
            postgresql_ops={"vec": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), unique=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(128))
    dim: Mapped[int] = mapped_column(SmallInteger)
    vec: Mapped[list[float]] = mapped_column(Vector(384))
    simhash: Mapped[int | None] = mapped_column(Integer, index=True)
    simhash_blocks: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))


class Cluster(Base, TimestampMixin):
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    key_terms: Mapped[list[str]] = mapped_column(default=list)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    doc_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("clusters.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[float | None] = mapped_column(Float)
