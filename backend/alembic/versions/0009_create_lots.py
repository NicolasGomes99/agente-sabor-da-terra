"""create lots

Revision ID: 0009_create_lots
Revises: 8a63f9d204e1
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_create_lots"
down_revision: str | Sequence[str] | None = "8a63f9d204e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("producer_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("availability_confirmed", sa.Boolean(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_lots_quantity_positive"),
        sa.CheckConstraint(
            "unit IS NULL OR unit ~ '[^[:space:]]'",
            name="ck_lots_unit_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["order_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["producer_id"], ["producers.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_lots_item_id", "lots", ["item_id"], unique=False)
    op.create_index("ix_lots_producer_id", "lots", ["producer_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lots_producer_id", table_name="lots")
    op.drop_index("ix_lots_item_id", table_name="lots")
    op.drop_table("lots")
