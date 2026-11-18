"""valor da hora de trabalho da empresa (custeio padrão da mão de obra)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-19 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('valor_hora', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_column('valor_hora')
