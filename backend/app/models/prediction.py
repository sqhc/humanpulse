"""预测登记：把推演链路里可证伪的节点登记下来，到期自动核对。

为什么必须有这张表：
推演要成为项目的可信差异点，就得能被证伪。只把概率写在视频里，
既无法核对也无法积累校准数据——过两个月回头看，没人知道当初说对了没有。

登记的是**每个节点的原始概率**（不是「涨/跌」这类事后可解释的话术），
到期用同一个判官模型对同一句话做一次是非判断，算出 Brier 并落库。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# open=待核对；hit/missed=已判定；unresolved=到期仍无法判断（顺延）；expired=太旧不再核对
PREDICTION_STATUSES = ("open", "hit", "missed", "unresolved", "expired")


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"
    __table_args__ = (
        # 到期核对任务的主查询：status='open' 且 due_at <= now
        Index("ix_predictions_status_due", "status", "due_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 溯源：来自哪期简报的哪条事件。用 SET NULL 而不是 CASCADE——
    # 简报被删不该让已经登记的预测消失（否则校准样本会被悄悄清空）
    brief_id: Mapped[int | None] = mapped_column(
        ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True
    )
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 链路位置：第几跳、哪个问题键（用于分跳/分问题统计准确率）
    hop: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    question_key: Mapped[str] = mapped_column(String(64), default="", server_default="")
    statement_zh: Mapped[str] = mapped_column(Text, default="")
    statement_en: Mapped[str] = mapped_column(Text, default="")

    predicted_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal(0))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)

    horizon_days: Mapped[int] = mapped_column(SmallInteger, default=14, server_default="14")
    due_at: Mapped[datetime]

    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # 到期复核时判官给的「该预测是否已兑现」概率
    resolved_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    # (p - outcome)^2，落库便于直接用 SQL 聚合整体校准
    brier: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)

    provider: Mapped[str] = mapped_column(String(32), default="", server_default="")
    model: Mapped[str] = mapped_column(String(64), default="", server_default="")
    # 复核时用了哪些文档作为证据
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)
