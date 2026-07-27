"""add product cost price, product variants and order item snapshots

Três mudanças relacionadas, todas aditivas e retrocompatíveis:

1. `products.cost_price` (opcional): preço de custo do produto, usado para
   calcular margem de lucro. Produtos existentes ficam com `cost_price`
   NULL — continuam funcionando exatamente como antes, só não mostram
   margem até o lojista preencher o custo.

2. Tabela `product_variants`: variações de tamanho/cor por produto, cada
   uma com seu próprio estoque e (opcionalmente) seu próprio preço. Um
   produto só passa a ter variações quando o lojista cadastra ao menos uma
   linha aqui — produtos sem nenhuma variação continuam usando
   `products.stock`/`products.price` diretamente, sem nenhuma mudança de
   comportamento (ver `Product.has_variants`/`Product.total_stock` em
   app/models.py).

3. `order_items.variant_id` / `variant_label` / `unit_cost`: snapshot de
   qual variação foi comprada e qual era o custo do produto no momento da
   venda. Todos opcionais — pedidos já existentes ficam com esses campos
   NULL e continuam sendo exibidos normalmente.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=True))

    op.create_table(
        "product_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("size", sa.String(length=40), nullable=True),
        sa.Column("color", sa.String(length=40), nullable=True),
        sa.Column("sku", sa.String(length=60), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "size", "color", name="uq_variant_product_size_color"),
    )
    with op.batch_alter_table("product_variants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_variants_product_id"), ["product_id"], unique=False
        )

    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("variant_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("variant_label", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.create_foreign_key(
            "fk_order_items_variant_id", "product_variants", ["variant_id"], ["id"], ondelete="SET NULL"
        )


def downgrade():
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_constraint("fk_order_items_variant_id", type_="foreignkey")
        batch_op.drop_column("unit_cost")
        batch_op.drop_column("variant_label")
        batch_op.drop_column("variant_id")

    with op.batch_alter_table("product_variants", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_variants_product_id"))
    op.drop_table("product_variants")

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("cost_price")
