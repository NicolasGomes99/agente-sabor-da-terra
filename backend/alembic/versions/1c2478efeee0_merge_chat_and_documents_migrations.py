"""merge chat and documents migrations

Revision ID: 1c2478efeee0
Revises: 0002_create_chat, 0002_create_documents
Create Date: 2026-11-17 12:53:49.596286

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '1c2478efeee0'
down_revision: str | Sequence[str] | None = ('0002_create_chat', '0002_create_documents')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
