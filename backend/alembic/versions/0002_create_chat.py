"""create chat sessions and messages tables

Revision ID: 0002_create_chat
Revises: 0001_create_users
Create Date: 2026-11-16 10:00:00
"""


from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_create_chat"
down_revision: str | None = "0001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

op.create_table(
    "chat_messages",
    sa.Column("id", sa.Uuid(as_uuid=True), nullable = False),
    sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("role", sa.String(length=16), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(
        ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
    ),
    sa.PrimaryKeyConstraint("id"),
)
op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")