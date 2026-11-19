"""create order items

Revision ID: bedbc9f628aa
Revises: cecd0d851e86
Create Date: 2026-11-18 17:58:11.358191

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bedbc9f628aa"
down_revision: str | Sequence[str] | None = "cecd0d851e86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Cria os itens sem alterar os pedidos existentes."""
    op.create_table(
        "order_items",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=3),
            nullable=False,
        ),
        sa.Column(
            "unit",
            sa.String(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity > 0 AND quantity <> 'NaN'::numeric",
            name="ck_order_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit ~ '[^[:space:]]'",
            name="ck_order_items_unit_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_order_items_order_id",
        "order_items",
        ["order_id"],
        unique=False,
    )

    op.create_index(
        "ix_order_items_product_id",
        "order_items",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove apenas a estrutura criada por esta migration."""
    op.drop_index(
        "ix_order_items_product_id",
        table_name="order_items",
    )

    op.drop_index(
        "ix_order_items_order_id",
        table_name="order_items",
    )

    op.drop_table("order_items")