"""execution journal

Engine phase (E5). One new table; nothing existing is altered.

The ``mode`` vocabulary is ('dry_run', 'testnet') and deliberately has no
mainnet member: no code path in this build can produce such a row, and a
vocabulary admitting one would make the table's own history ambiguous about
whether this build ever traded real money.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'execution_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column(
            'mode',
            sa.Enum('dry_run', 'testnet', name='execution_order_mode', native_enum=False),
            nullable=False,
        ),
        sa.Column('asset', sa.String(length=32), nullable=False),
        sa.Column('direction', sa.String(length=8), nullable=False),
        sa.Column('size', sa.Float(), nullable=False),
        sa.Column('reference_price', sa.Float(), nullable=False),
        sa.Column('limit_price', sa.Float(), nullable=False),
        sa.Column('stop_price', sa.Float(), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=True),
        sa.Column('stage_scale', sa.Float(), nullable=True),
        sa.Column('requested_risk_usd', sa.Float(), nullable=True),
        sa.Column('realised_risk_usd', sa.Float(), nullable=True),
        sa.Column('accepted', sa.Boolean(), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'simulated', 'filled', 'resting', 'rejected', 'error',
                name='execution_order_status', native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('venue_order_id', sa.String(length=64), nullable=True),
        sa.Column('filled_size', sa.Float(), nullable=False),
        sa.Column('average_price', sa.Float(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('intent', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('receipt', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('system_id', sa.Integer(), nullable=True),
        sa.Column('strategy_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id'),
    )
    op.create_index(
        'ix_execution_orders_mode_created_at',
        'execution_orders',
        ['mode', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_execution_orders_mode_created_at', table_name='execution_orders')
    op.drop_table('execution_orders')
