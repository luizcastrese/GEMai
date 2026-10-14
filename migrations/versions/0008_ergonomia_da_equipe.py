"""ergonomia da equipe: perfil da equipe na unidade e altura da bancada no local

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('perfil_equipe_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('espacos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('altura_trabalho_m', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('espacos', schema=None) as batch_op:
        batch_op.drop_column('altura_trabalho_m')
    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.drop_column('perfil_equipe_id')
