"""store socials and order payment method

Revision ID: 7d3a0b5c8e2f
Revises: 0a0fb23259f4
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "7d3a0b5c8e2f"
down_revision = "0a0fb23259f4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stores", schema=None) as batch_op:
        batch_op.add_column(sa.Column("instagram_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("facebook_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("tiktok_url", sa.Text(), nullable=True))

    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payment_method", sa.String(length=60), nullable=True))


def downgrade():
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("payment_method")

    with op.batch_alter_table("stores", schema=None) as batch_op:
        batch_op.drop_column("tiktok_url")
        batch_op.drop_column("facebook_url")
        batch_op.drop_column("instagram_url")
