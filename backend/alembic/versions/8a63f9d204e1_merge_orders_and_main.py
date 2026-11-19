"""merge orders and main

Revision ID: 8a63f9d204e1
Revises: d7a91f3c2b60, 0008_merge_triage_main
Create Date: 2026-11-19 15:31:00.819492

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a63f9d204e1'
down_revision: Union[str, Sequence[str], None] = ('d7a91f3c2b60', '0008_merge_triage_main')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
