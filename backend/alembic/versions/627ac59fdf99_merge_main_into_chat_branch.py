"""merge main into chat branch

Revision ID: 627ac59fdf99
Revises: 0005_chat_message_role_enum, 5f2652d96d4f
Create Date: 2026-11-19 08:41:52.933746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '627ac59fdf99'
down_revision: Union[str, Sequence[str], None] = ('0005_chat_message_role_enum', '5f2652d96d4f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
