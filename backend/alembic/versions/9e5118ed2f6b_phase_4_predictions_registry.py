"""phase 4 predictions registry

只新建 predictions 表。

注意：autogenerate 同时报了一个 ix_documents_feed 的「变化」，
那是它读不懂表达式索引导致的误报（原索引是 published_at DESC, id DESC），
并非真实差异；在 documents 这种大表上重建索引纯属浪费且有风险，已手工剔除。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9e5118ed2f6b"
down_revision: str | None = "64ff16b66a50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brief_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("cluster_id", sa.Integer(), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("hop", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("question_key", sa.String(length=64), server_default="", nullable=False),
        sa.Column("statement_zh", sa.Text(), nullable=False),
        sa.Column("statement_en", sa.Text(), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("horizon_days", sa.SmallInteger(), server_default="14", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_probability", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("brier", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("provider", sa.String(length=32), server_default="", nullable=False),
        sa.Column("model", sa.String(length=64), server_default="", nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brief_id"], ["briefs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cluster_id"], ["clusters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_predictions_brief_id"), "predictions", ["brief_id"], unique=False)
    op.create_index(op.f("ix_predictions_entity_id"), "predictions", ["entity_id"], unique=False)
    op.create_index("ix_predictions_status_due", "predictions", ["status", "due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_predictions_status_due", table_name="predictions")
    op.drop_index(op.f("ix_predictions_entity_id"), table_name="predictions")
    op.drop_index(op.f("ix_predictions_brief_id"), table_name="predictions")
    op.drop_table("predictions")
