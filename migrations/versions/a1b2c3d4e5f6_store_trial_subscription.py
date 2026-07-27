"""store trial and subscription fields

Revision ID: a1b2c3d4e5f6
Revises: 7d3a0b5c8e2f
Create Date: 2026-06-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta

revision = "a1b2c3d4e5f6"
down_revision = "7d3a0b5c8e2f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stores", schema=None) as batch_op:
        batch_op.add_column(sa.Column("trial_ends_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("subscription_active", sa.Boolean(), nullable=False, server_default="0")
        )

    # Lojas já existentes recebem trial de 14 dias a partir de agora
    op.execute(
        "UPDATE stores SET trial_ends_at = datetime('now', '+14 days') WHERE trial_ends_at IS NULL"
    )


def downgrade():
    with op.batch_alter_table("stores", schema=None) as batch_op:
        batch_op.drop_column("subscription_active")
        batch_op.drop_column("trial_ends_at")
