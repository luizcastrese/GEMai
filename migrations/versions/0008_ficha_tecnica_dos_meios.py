"""ficha técnica dos meios: marca/modelo no recurso e rastro da fonte nos parâmetros

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-30 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('marca', sa.String(length=120), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('modelo', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('modelo_confirmado', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('parametros', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fonte_url', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('fonte_data', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('confianca', sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('parametros', schema=None) as batch_op:
        batch_op.drop_column('confianca')
        batch_op.drop_column('fonte_data')
        batch_op.drop_column('fonte_url')
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.drop_column('modelo_confirmado')
        batch_op.drop_column('modelo')
        batch_op.drop_column('marca')
