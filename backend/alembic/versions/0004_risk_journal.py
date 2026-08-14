"""risk_rules + journal_entries + daily_risk_logs (Phase 4, T4)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'risk_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('system_id', sa.Integer(), nullable=True),
        sa.Column('max_daily_r', sa.Float(), nullable=True),
        sa.Column('max_weekly_r', sa.Float(), nullable=True),
        sa.Column('max_monthly_r', sa.Float(), nullable=True),
        sa.Column('max_trades_per_day', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('entry_type', sa.String(length=12), server_default='note', nullable=False),
        sa.Column('system_id', sa.Integer(), nullable=True),
        sa.Column('trade_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=256), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'daily_risk_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('realized_r', sa.Float(), nullable=True),
        sa.Column('trade_count', sa.Integer(), nullable=True),
        sa.Column('halted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('risk_rule_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['risk_rule_id'], ['risk_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('log_date'),
    )

    # Seed the default global risk rule (values from the master prompt: 3/5).
    op.bulk_insert(
        sa.table(
            'risk_rules',
            sa.column('name', sa.String),
            sa.column('max_daily_r', sa.Float),
            sa.column('max_weekly_r', sa.Float),
            sa.column('active', sa.Boolean),
        ),
        [{'name': 'default', 'max_daily_r': 3, 'max_weekly_r': 5, 'active': True}],
    )


def downgrade() -> None:
    op.drop_table('daily_risk_logs')
    op.drop_table('journal_entries')
    op.drop_table('risk_rules')
