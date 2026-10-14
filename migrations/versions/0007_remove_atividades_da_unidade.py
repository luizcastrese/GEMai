"""as atividades passam a ser deduzidas das peças: remove a coluna da unidade

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.drop_column('atividades')


def downgrade() -> None:
    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('atividades', sa.JSON(), nullable=True))
