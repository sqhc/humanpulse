"""抓取批次与文档（原始条目）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 文档状态机：pending → enriched / rejected / deduped / failed
DOCUMENT_STATUSES = ("pending", "enriched", "rejected", "deduped", "failed")


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running", server_default="running")
    items_seen: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_new: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal(0), server_default="0"
    )


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_feed", text("published_at DESC, id DESC")),
        Index("ix_documents_status_fetched", "status", text("fetched_at DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    fetch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="SET NULL"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    language: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16), default="news", server_default="news")
    excerpt: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    simhash: Mapped[int | None] = mapped_column(BigInteger, index=True)
    simhash_blocks: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(64))
