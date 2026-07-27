"""add subscription_payments table

Cria a tabela que guarda o histórico de renovações e suspensões de
assinatura feitas pelo superadmin. Antes dessa migration, cada ação de
renovação só sobrescrevia `stores.paid_until`, sem deixar nenhum rastro de
quando ou por quanto tempo a assinatura foi renovada. Essa tabela alimenta
tanto a área "Minha assinatura" do lojista (histórico de pagamentos) quanto
relatórios financeiros do superadmin (MRR, renovações por período etc).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subscription_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Enum('renew', 'suspend'), nullable=False),
        sa.Column('months', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('registered_by_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.ForeignKeyConstraint(['registered_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('subscription_payments', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_subscription_payments_store_id'), ['store_id'], unique=False
        )


def downgrade():
    with op.batch_alter_table('subscription_payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscription_payments_store_id'))
    op.drop_table('subscription_payments')
