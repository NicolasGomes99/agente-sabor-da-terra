"""merge main into chat branch

Revision ID: 627ac59fdf99
Revises: 0005_chat_message_role_enum, 5f2652d96d4f
Create Date: 2026-11-19 08:41:52.933746

"""

from collections.abc import Sequence

revision: str = "627ac59fdf99"
down_revision: str | Sequence[str] | None = (
    "0005_chat_message_role_enum",
    "5f2652d96d4f",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
