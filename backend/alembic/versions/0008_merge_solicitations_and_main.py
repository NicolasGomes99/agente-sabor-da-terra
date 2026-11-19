"""merge solicitation and main migration histories

Revision ID: 0008_merge_triage_main
Revises: 0007_create_solicitations, 0007_chunk_csv_record
Create Date: 2026-11-19
"""

from collections.abc import Sequence

revision: str = "0008_merge_triage_main"
down_revision: str | Sequence[str] | None = (
    "0007_create_solicitations",
    "0007_chunk_csv_record",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
