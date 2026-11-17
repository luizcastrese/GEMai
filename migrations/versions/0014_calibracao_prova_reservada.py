"""calibração: erro típico sem calibração, com fator constante e com o modelo proposto (prova com dados reservados)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-17 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('calibracoes_modulo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('erro_sem_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('erro_constante_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('erro_com_pct', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('calibracoes_modulo', schema=None) as batch_op:
        batch_op.drop_column('erro_com_pct')
        batch_op.drop_column('erro_constante_pct')
        batch_op.drop_column('erro_sem_pct')
