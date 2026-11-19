"""add csv record columns to document_chunks

Revision ID: 0007_chunk_csv_record
Revises: 627ac59fdf99
Create Date: 2026-11-19 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_chunk_csv_record"
down_revision: str | Sequence[str] | None = "627ac59fdf99"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("record_id", sa.String(), nullable=True))
    op.add_column("document_chunks", sa.Column("record_fields", sa.JSON(), nullable=True))
    op.create_index(
        "ix_document_chunks_document_id_record_id",
        "document_chunks",
        ["document_id", "record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_id_record_id", table_name="document_chunks")
    op.drop_column("document_chunks", "record_fields")
    op.drop_column("document_chunks", "record_id")