"""produto como família: campos de especificação; plano guarda a variante (valores e estrutura)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-16 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('produtos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('campos_especificacao', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('planos_trabalho', schema=None) as batch_op:
        batch_op.add_column(sa.Column('especificacoes', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('estrutura', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('planos_trabalho', schema=None) as batch_op:
        batch_op.drop_column('estrutura')
        batch_op.drop_column('especificacoes')
    with op.batch_alter_table('produtos', schema=None) as batch_op:
        batch_op.drop_column('campos_especificacao')
