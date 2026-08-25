"""strategies, their versions, and backtest runs

Engine phase (E2.3). Three new tables; nothing existing is altered.

The ``systems.provenance`` vocabulary gains 'engine', but that needs no DDL:
the column is a plain VARCHAR(12) — ``native_enum=False`` without a check
constraint — and 'engine' fits. The change lives in the Python tuple, and
existing rows keep whatever provenance they were imported with.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'strategies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('asset', sa.String(length=32), nullable=False),
        sa.Column('timeframe', sa.String(length=16), nullable=False),
        sa.Column(
            'rules',
            sa.Enum('declarative', 'python', name='strategy_rules', native_enum=False),
            server_default='declarative',
            nullable=False,
        ),
        sa.Column('current_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'strategy_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strategy_id', 'version', name='uq_strategy_version'),
    )

    op.create_table(
        'backtest_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('strategy_version_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ok', 'failed', name='backtest_status', native_enum=False),
            nullable=False,
        ),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('bars', sa.Integer(), nullable=False),
        sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('trades', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('overrides', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # SET NULL, not CASCADE: deleting the materialised system should not
        # erase the record that the run happened.
        sa.Column('system_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['strategy_version_id'], ['strategy_versions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_backtest_runs_strategy_id_created_at',
        'backtest_runs',
        ['strategy_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_backtest_runs_strategy_id_created_at', table_name='backtest_runs')
    op.drop_table('backtest_runs')
    op.drop_table('strategy_versions')
    op.drop_table('strategies')
