"""provenance & source_engine on systems

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'systems',
        sa.Column(
            'provenance',
            sa.Enum('manual', 'programmatic', name='system_provenance', native_enum=False),
            server_default='manual',
            nullable=False,
        ),
    )
    op.add_column(
        'systems',
        sa.Column('source_engine', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('systems', 'source_engine')
    op.drop_column('systems', 'provenance')
