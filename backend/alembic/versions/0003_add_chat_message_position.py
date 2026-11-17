"""add persistent chat message ordering

Revision ID: 0003_add_chat_message_position
Revises: 1c2478efeee0
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_chat_message_position"
down_revision: str | None = "1c2478efeee0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("position", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            WITH ordered_messages AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY session_id
                           ORDER BY created_at ASC, id ASC
                       ) AS position
                FROM chat_messages
            )
            UPDATE chat_messages
            SET position = ordered_messages.position
            FROM ordered_messages
            WHERE chat_messages.id = ordered_messages.id
            """
        )
    )
    op.alter_column(
        "chat_messages",
        "position",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_chat_messages_session_position",
        "chat_messages",
        ["session_id", "position"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_chat_messages_session_position",
        "chat_messages",
        type_="unique",
    )
    op.drop_column("chat_messages", "position")
