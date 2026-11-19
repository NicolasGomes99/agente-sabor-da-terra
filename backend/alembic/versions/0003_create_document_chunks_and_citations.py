"""create document_chunks and citations tables

Revision ID: 0003_create_citations
Revises: 1c2478efeee0
Create Date: 2026-11-17 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_create_citations"
down_revision: str | Sequence[str] | None = "1c2478efeee0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
    )

    op.create_table(
        "citations",
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("chunk_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("message_id", "chunk_id"),
    )
    op.create_index(
        "ix_citations_chunk_id",
        "citations",
        ["chunk_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_citations_chunk_id", table_name="citations")
    op.drop_table("citations")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")