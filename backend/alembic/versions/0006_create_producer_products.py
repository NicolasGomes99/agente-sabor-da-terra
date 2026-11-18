"""create producer products table

Revision ID: 0006_create_producer_products
Revises: 0005_create_producers
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_create_producer_products"
down_revision: str | None = "0005_create_producers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "producer_products",
        sa.Column("producer_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["producer_id"], ["producers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("producer_id", "product_id"),
    )
    op.create_index(
        "ix_producer_products_product_id", "producer_products", ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_producer_products_product_id", table_name="producer_products")
    op.drop_table("producer_products")
