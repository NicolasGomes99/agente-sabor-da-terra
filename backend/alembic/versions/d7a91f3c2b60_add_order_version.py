"""Add optimistic concurrency version to orders.

Revision ID: d7a91f3c2b60
Revises: bedbc9f628aa
"""
import sqlalchemy as sa

from alembic import op

revision = "d7a91f3c2b60"
down_revision = "bedbc9f628aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint("ck_orders_version_positive", "orders", "version >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_orders_version_positive", "orders", type_="check")
    op.drop_column("orders", "version")
