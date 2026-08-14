"""live_corrections

Phase 8: (a) Live-Trades ohne System erlauben (freier Trade), (b) Platz für die
neuen Ledger-Änderungsarten der Kontostand-Rückabwicklung.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Freier Live-Trade ohne System (Asset dann frei wählbar).
    op.alter_column(
        'live_trades', 'system_id', existing_type=sa.Integer(), nullable=True
    )
    # 'trade_delete'/'trade_correction' passen nicht in VARCHAR(11).
    op.alter_column(
        'account_balance',
        'change_type',
        existing_type=sa.String(length=11),
        type_=sa.String(length=24),
        existing_nullable=False,
        existing_server_default='manual',
    )


def downgrade() -> None:
    # Rückabwicklungs-Zeilen zurück auf einen Wert, der in VARCHAR(11) passt.
    op.execute(
        "UPDATE account_balance SET change_type = 'manual' "
        "WHERE change_type NOT IN ('initial', 'manual', 'trade_close')"
    )
    op.alter_column(
        'account_balance',
        'change_type',
        existing_type=sa.String(length=24),
        type_=sa.String(length=11),
        existing_nullable=False,
        existing_server_default='manual',
    )
    # Verwaiste (system-lose) Trades entfernen, sonst schlägt NOT NULL fehl.
    op.execute("DELETE FROM live_trades WHERE system_id IS NULL")
    op.alter_column(
        'live_trades', 'system_id', existing_type=sa.Integer(), nullable=False
    )
