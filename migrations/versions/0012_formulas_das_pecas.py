"""fórmulas que ligam as medidas do pedido às peças e aos fixadores

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-16 22:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('componentes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('formulas', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('ligacoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('formula_fixadores', sa.String(length=200), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('ligacoes', schema=None) as batch_op:
        batch_op.drop_column('formula_fixadores')
    with op.batch_alter_table('componentes', schema=None) as batch_op:
        batch_op.drop_column('formulas')
