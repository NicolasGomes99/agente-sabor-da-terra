"""create chat_operations table for persistent operation tracking and concurrency control

Revision ID: 0011_chat_operations
Revises: 0010_chat_agent_metadata
Create Date: 2026-11-19 22:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_chat_operations"
down_revision: str | Sequence[str] | None = "0010_chat_agent_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("operation_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("session_generation", sa.BigInteger(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("selected_flow", sa.String(length=32), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_chat_operations_status",
        ),
        sa.CheckConstraint(
            "attempt >= 1",
            name="ck_chat_operations_attempt_positive",
        ),
        sa.CheckConstraint(
            "session_generation >= 1",
            name="ck_chat_operations_generation_positive",
        ),
        sa.CheckConstraint(
            "selected_flow IS NULL OR selected_flow IN ('triage', 'consultation')",
            name="ck_chat_operations_selected_flow",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["chat_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "operation_key",
            name="uq_chat_operations_session_key",
        ),
    )
    op.create_index(
        "ix_chat_operations_session_id",
        "chat_operations",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_operations_session_generation",
        "chat_operations",
        ["session_id", "session_generation"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_operations_session_generation",
        table_name="chat_operations",
    )
    op.drop_index(
        "ix_chat_operations_session_id",
        table_name="chat_operations",
    )
    op.drop_table("chat_operations")
