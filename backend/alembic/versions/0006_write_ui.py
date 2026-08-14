"""write-ui: systems.origin/user_overrides + system_concepts.match_reason

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-12 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'systems',
        sa.Column(
            'origin',
            sa.Enum('import', 'ui', name='system_origin', native_enum=False),
            server_default='import',
            nullable=False,
        ),
    )
    op.add_column(
        'systems',
        sa.Column(
            'user_overrides',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        'system_concepts',
        sa.Column('match_reason', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('system_concepts', 'match_reason')
    op.drop_column('systems', 'user_overrides')
    op.drop_column('systems', 'origin')
