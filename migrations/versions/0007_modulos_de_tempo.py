"""módulos de tempo: passos do plano e operações guardam o módulo e as condições

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-29 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('plano_passos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modulo', sa.String(length=30), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('modulo_versao', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('parametros_modulo', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('coeficientes', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('tempo_normal_min', sa.Float(), nullable=True))
    with op.batch_alter_table('operacoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modulo', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('modulo_parametros', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('operacoes', schema=None) as batch_op:
        batch_op.drop_column('modulo_parametros')
        batch_op.drop_column('modulo')
    with op.batch_alter_table('plano_passos', schema=None) as batch_op:
        batch_op.drop_column('tempo_normal_min')
        batch_op.drop_column('coeficientes')
        batch_op.drop_column('parametros_modulo')
        batch_op.drop_column('modulo_versao')
        batch_op.drop_column('modulo')
