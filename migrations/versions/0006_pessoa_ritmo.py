"""pessoa com perfil e ritmo

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import app.models


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('pessoas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('perfil_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('ritmo_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('ritmo_origem', sa.String(length=20), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('ritmo_amostras', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('ritmo_calibrado_em', app.models.UTCDateTime(), nullable=True))
        batch_op.create_foreign_key('fk_pessoas_perfil', 'perfis_mao_de_obra', ['perfil_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('pessoas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pessoas_perfil', type_='foreignkey')
        batch_op.drop_column('ritmo_calibrado_em')
        batch_op.drop_column('ritmo_amostras')
        batch_op.drop_column('ritmo_origem')
        batch_op.drop_column('ritmo_pct')
        batch_op.drop_column('perfil_id')
