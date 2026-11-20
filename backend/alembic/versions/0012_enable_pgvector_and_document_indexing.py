"""enable pgvector extension and add document indexing metadata

Revision ID: 0012_pgvector_document_indexing
Revises: 0011_chat_operations
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_pgvector_document_indexing"
down_revision: str | Sequence[str] | None = "0011_chat_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "documents",
        sa.Column("source_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "processing_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_documents_processing_status",
        "documents",
        "processing_status IN ('pending', 'processing', 'indexed', 'failed')",
    )
    op.create_index(
        "uq_documents_source_path",
        "documents",
        ["source_path"],
        unique=True,
        postgresql_where=sa.text("source_path IS NOT NULL"),
    )

    # Preserva documentos preexistentes que já possuíam trechos persistidos.
    op.execute(
        """
        UPDATE documents
        SET processing_status = 'indexed'
        WHERE EXISTS (
            SELECT 1
            FROM document_chunks
            WHERE document_chunks.document_id = documents.id
        )
        """
    )

    op.execute(
        """
        ALTER TABLE document_chunks
        ALTER COLUMN embedding TYPE vector
        USING CASE
            WHEN embedding IS NULL OR btrim(embedding) = '' THEN NULL
            ELSE embedding::vector
        END
        """
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column("chunk_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index(
        "ix_document_chunks_document_id_chunk_key",
        "document_chunks",
        ["document_id", "chunk_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_chunks_document_id_chunk_key",
        table_name="document_chunks",
    )
    op.drop_column("document_chunks", "is_active")
    op.drop_column("document_chunks", "chunk_key")
    op.drop_column("document_chunks", "chunk_index")
    op.drop_column("document_chunks", "embedding_model")
    op.execute(
        """
        ALTER TABLE document_chunks
        ALTER COLUMN embedding TYPE text
        USING embedding::text
        """
    )

    op.drop_index("uq_documents_source_path", table_name="documents")
    op.drop_constraint(
        "ck_documents_processing_status",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "indexed_at")
    op.drop_column("documents", "processing_error")
    op.drop_column("documents", "processing_status")
    op.drop_column("documents", "content_sha256")
    op.drop_column("documents", "source_path")
