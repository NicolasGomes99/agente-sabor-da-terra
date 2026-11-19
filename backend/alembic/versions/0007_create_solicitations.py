"""create solicitations and allow triage sessions without an owner

Revision ID: 0007_create_solicitations
Revises: 0005_chat_message_role_enum
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_create_solicitations"
down_revision: str | Sequence[str] | None = "0005_chat_message_role_enum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_TYPE = postgresql.ENUM(
    "recebida",
    "em_analise",
    "finalizada",
    name="solicitation_status",
)
TYPE_TYPE = postgresql.ENUM(
    "pedido",
    "consulta",
    "oferta",
    "comunicado",
    "nao_identificado",
    name="solicitation_type",
)
URGENCY_TYPE = postgresql.ENUM(
    "urgente",
    "normal",
    "indeterminada",
    name="solicitation_urgency",
)


def upgrade() -> None:
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )

    STATUS_TYPE.create(op.get_bind())
    TYPE_TYPE.create(op.get_bind())
    URGENCY_TYPE.create(op.get_bind())

    op.create_table(
        "solicitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "recebida",
                "em_analise",
                "finalizada",
                name="solicitation_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "request_type",
            postgresql.ENUM(
                "pedido",
                "consulta",
                "oferta",
                "comunicado",
                "nao_identificado",
                name="solicitation_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "urgency",
            postgresql.ENUM(
                "urgente",
                "normal",
                "indeterminada",
                name="solicitation_urgency",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            name="uq_solicitations_session_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("solicitations")

    STATUS_TYPE.drop(op.get_bind())
    TYPE_TYPE.drop(op.get_bind())
    URGENCY_TYPE.drop(op.get_bind())

    op.execute("DELETE FROM chat_sessions WHERE user_id IS NULL")
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
