"""create lot imports

Revision ID: 0010_create_lot_imports
Revises: 0009_create_lots
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_create_lot_imports"
down_revision: str | Sequence[str] | None = "0009_create_lots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lot_imports",
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("source_file", sa.String(), nullable=False),
        sa.Column("record_id", sa.String(), nullable=False),
        sa.Column("record_fields", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lot_id"),
        sa.UniqueConstraint(
            "source_file",
            "record_id",
            name="uq_lot_imports_source_record",
        ),
    )


def downgrade() -> None:
    op.drop_table("lot_imports")
