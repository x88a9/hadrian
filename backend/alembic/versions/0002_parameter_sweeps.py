"""parameter_sweeps table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10 16:03:10.826178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'parameter_sweeps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=128), nullable=True),
        sa.Column('param_x', sa.String(length=64), server_default='tp_r', nullable=False),
        sa.Column('param_y', sa.String(length=64), server_default='sl_r', nullable=False),
        sa.Column('metric', sa.String(length=64), server_default='ev', nullable=False),
        sa.Column('points', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('parameter_sweeps')
