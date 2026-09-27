"""简报：日报/周报与其条目。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

BRIEF_KINDS = ("daily", "weekly")


class Brief(Base, TimestampMixin):
    __tablename__ = "briefs"
    __table_args__ = (Index("ix_briefs_kind_period", "kind", text("period_start DESC")),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    language: Mapped[str] = mapped_column(
        String(16), default="bilingual", server_default="bilingual"
    )
    title: Mapped[str] = mapped_column(String(300))
    markdown: Mapped[str] = mapped_column(Text, default="")
    # 结构化内容（BriefContent）：前端按语言渲染，Markdown 由服务端确定性渲染
    structured: Mapped[dict[str, Any]] = mapped_column(default=dict)
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(16), default="")
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal(0), server_default="0"
    )


class BriefItem(Base):
    __tablename__ = "brief_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("briefs.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    rationale: Mapped[str | None] = mapped_column(String(200))
