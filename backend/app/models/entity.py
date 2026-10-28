"""实体与提及：用于人物/组织/地点/事件的时间线。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

ENTITY_KINDS = ("person", "org", "place", "event")


class Entity(Base, TimestampMixin):
    """一个可追踪的实体；key 是 kind + 归一化名字，用来去重。

    跨语言别名（特朗普 / Trump / Donald Trump）本表**不会自动合并**——需要人工别名表
    或外部知识库（如 Wikidata）支持，见 ADR-0007。
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(300), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    aliases: Mapped[list[str]] = mapped_column(default=list)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(32))
    # 指向合并后的规范实体；非空表示"本行只是某个实体的别名写法"（保留用于审计）
    canonical_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "entities.id",
            ondelete="SET NULL",
            name="fk_entities_canonical_entity_id",
        ),
        nullable=True,
        index=True,
    )


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        UniqueConstraint("entity_id", "document_id", name="uq_entity_mentions_entity_document"),
        Index("ix_entity_mentions_entity_created", "entity_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True
    )
    salience: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AliasReview(Base, TimestampMixin):
    """实体别名审核队列：存储由判官判定为 'review' 的候选对。"""

    __tablename__ = "alias_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    left_id: Mapped[int] = mapped_column(Integer, index=True)
    right_id: Mapped[int] = mapped_column(Integer, index=True)
    left_name: Mapped[str] = mapped_column(String(200))
    right_name: Mapped[str] = mapped_column(String(200))
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    shared_documents: Mapped[int] = mapped_column(Integer)
    jaccard: Mapped[float] = mapped_column(Float)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolution: Mapped[str | None] = mapped_column(String(16))  # 'merge' | 'reject'
