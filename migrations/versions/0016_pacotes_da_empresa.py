"""pacotes de segmento ativos por empresa (o pacote base vale para todas)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-18 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # empresas que já existem continuam com o pacote de marcenaria (o comportamento de antes)
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pacotes', sa.JSON(), nullable=False, server_default='["marcenaria"]'))


def downgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_column('pacotes')
