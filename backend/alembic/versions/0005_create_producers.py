"""create producers table

Revision ID: 0005_create_producers
Revises: 0004_create_products
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_create_producers"
down_revision: str | None = "0004_create_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "producers",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("cpf", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("municipality", sa.String(), nullable=True),
        sa.CheckConstraint(
            "code ~ '[^[:space:]]'", name="ck_producers_code_not_blank"
        ),
        sa.CheckConstraint(
            "name ~ '[^[:space:]]'", name="ck_producers_name_not_blank"
        ),
        sa.CheckConstraint(
            "cpf ~ '[^[:space:]]'", name="ck_producers_cpf_not_blank"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("cpf"),
    )


def downgrade() -> None:
    op.drop_table("producers")
