"""calibração por família: o fator do módulo passa a escalar com o porte do pedido

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-17 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('calibracoes_modulo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('produto_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('expoente', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('porte_ref', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('porte_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('porte_max', sa.Float(), nullable=True))
        batch_op.create_foreign_key('fk_calib_produto', 'produtos', ['produto_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('calibracoes_modulo', schema=None) as batch_op:
        batch_op.drop_constraint('fk_calib_produto', type_='foreignkey')
        batch_op.drop_column('porte_max')
        batch_op.drop_column('porte_min')
        batch_op.drop_column('porte_ref')
        batch_op.drop_column('expoente')
        batch_op.drop_column('produto_id')
