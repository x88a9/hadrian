"""concepts + system_concepts tables (Phase 4, T1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# D1 seed: concept names only (no assignments).
CONCEPT_NAMES = [
    "Open Interest",
    "Funding",
    "Session Volume Profile",
    "Order Flow",
    "Liquidity",
    "Volume Profile",
]


def upgrade() -> None:
    op.create_table(
        'concepts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'system_concepts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.Integer(), nullable=False),
        sa.Column('concept_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=9), server_default='manual', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['concept_id'], ['concepts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'concept_id', name='uq_system_concept'),
    )

    op.bulk_insert(
        sa.table('concepts', sa.column('name', sa.String)),
        [{'name': name} for name in CONCEPT_NAMES],
    )


def downgrade() -> None:
    op.drop_table('system_concepts')
    op.drop_table('concepts')
