"""add adjustment action type to subscription_payments

Adiciona "adjustment" como terceiro valor possível de
`subscription_payments.action`, distinto de "renew" (renovação paga) e
"suspend" (suspensão). Usado quando o superadmin corrige manualmente a
data de vencimento de uma loja sem que isso represente um pagamento real —
antes essas correções eram gravadas como "renew" com `months`/`amount`
nulos, o que misturava ajustes administrativos com renovações pagas de
fato no histórico e nos cálculos de receita.

Não há dados a migrar: registros antigos de ajuste de data (identificáveis
por `action="renew"` com `months` nulo) continuam como estão — a separação
vale a partir de agora. Quem quiser reclassificar o histórico antigo pode
rodar manualmente:
    UPDATE subscription_payments SET action='adjustment'
    WHERE action='renew' AND months IS NULL;

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None

OLD_ENUM = sa.Enum("renew", "suspend", name="subscription_payments_action")
NEW_ENUM = sa.Enum("renew", "adjustment", "suspend", name="subscription_payments_action")


def upgrade():
    with op.batch_alter_table("subscription_payments", schema=None) as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=OLD_ENUM,
            type_=NEW_ENUM,
            existing_nullable=False,
        )


def downgrade():
    # Reclassifica eventuais "adjustment" como "renew" antes de remover o
    # valor do enum, para não deixar linhas com um valor que não existirá mais.
    op.execute("UPDATE subscription_payments SET action='renew' WHERE action='adjustment'")
    with op.batch_alter_table("subscription_payments", schema=None) as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=NEW_ENUM,
            type_=OLD_ENUM,
            existing_nullable=False,
        )
