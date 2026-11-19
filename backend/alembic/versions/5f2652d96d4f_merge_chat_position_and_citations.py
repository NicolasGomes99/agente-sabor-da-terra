"""merge chat position and citations

Revision ID: 5f2652d96d4f
Revises: 0003_add_chat_message_position, 0003_create_citations
Create Date: 2026-11-18 23:25:17.336450

"""

from collections.abc import Sequence

revision: str = "5f2652d96d4f"
down_revision: str | Sequence[str] | None = (
    "0003_add_chat_message_position",
    "0003_create_citations",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
