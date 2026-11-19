"""Use a PostgreSQL enum for chat message roles.

Revision ID: 0005_chat_message_role_enum
Revises: 0004_create_products
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_chat_message_role_enum"
down_revision: str | None = "0004_create_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_TYPE = postgresql.ENUM("USER", "AGENT", name="chat_message_role")


def upgrade() -> None:
    ROLE_TYPE.create(op.get_bind())
    op.alter_column(
        "chat_messages",
        "role",
        existing_type=sa.String(16),
        existing_nullable=False,
        type_=ROLE_TYPE,
        # The enum cast rejects unknown roles and rolls back the migration.
        postgresql_using="""
            (CASE role
                WHEN 'user' THEN 'USER'
                WHEN 'assistant' THEN 'AGENT'
                ELSE role
            END)::chat_message_role
        """,
    )


def downgrade() -> None:
    op.alter_column(
        "chat_messages",
        "role",
        existing_type=ROLE_TYPE,
        existing_nullable=False,
        type_=sa.String(16),
        postgresql_using="""
            (CASE role
                WHEN 'USER' THEN 'user'
                WHEN 'AGENT' THEN 'assistant'
            END)::varchar(16)
        """,
    )
    ROLE_TYPE.drop(op.get_bind())
