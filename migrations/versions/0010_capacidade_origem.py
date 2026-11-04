"""origem da capacidade do equipamento (medido ou estimado pela IA)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-04 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('capacidade_origem', sa.String(length=10), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.drop_column('capacidade_origem')
