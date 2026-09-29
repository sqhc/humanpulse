"""phase 3 entity aliases

Revision ID: 64ff16b66a50
Revises: 92ce9d6b5273
Create Date: 2026-09-29 13:42:22.638959+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '64ff16b66a50'
down_revision: str | None = '92ce9d6b5273'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FK_NAME = 'fk_entities_canonical_entity_id'


def upgrade() -> None:
    op.add_column('entities', sa.Column('canonical_entity_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_entities_canonical_entity_id'), 'entities', ['canonical_entity_id'], unique=False)
    # 必须显式命名：匿名约束在 downgrade 里没法 drop（autogenerate 默认给 None）
    op.create_foreign_key(
        FK_NAME, 'entities', 'entities', ['canonical_entity_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, 'entities', type_='foreignkey')
    op.drop_index(op.f('ix_entities_canonical_entity_id'), table_name='entities')
    op.drop_column('entities', 'canonical_entity_id')
