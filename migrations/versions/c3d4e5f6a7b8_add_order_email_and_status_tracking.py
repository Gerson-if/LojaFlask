"""add customer_email and status_updated_at to orders

Adiciona uma coluna própria para o e-mail do cliente no pedido (antes esse
dado era gravado manualmente dentro de `notes`, misturado com observações
livres). Também adiciona `status_updated_at` para saber quando o status do
pedido mudou pela última vez, e um índice em `status` para acelerar os
filtros usados nas telas de pedidos (loja e admin da plataforma).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_email", sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column("status_updated_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_orders_status", ["status"], unique=False)


def downgrade():
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index("ix_orders_status")
        batch_op.drop_column("status_updated_at")
        batch_op.drop_column("customer_email")
