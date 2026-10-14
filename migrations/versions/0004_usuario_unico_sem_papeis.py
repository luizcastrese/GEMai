"""usuario unico sem papeis

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14 13:20:12.157978
"""
from alembic import op
import sqlalchemy as sa
import app.models


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Antes, administradores viam todas as unidades por serem admin. Agora "nenhuma unidade atribuída" significa
    # "todas": remove as atribuições deles para que não percam acesso.
    op.execute("DELETE FROM usuario_unidades WHERE usuario_id IN (SELECT id FROM usuarios WHERE perfil = 'admin')")
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('perfil')


def downgrade() -> None:
    # Reatribui o papel mais amplo a todos (ninguém perde acesso ao voltar).
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('perfil', sa.VARCHAR(length=20), nullable=False, server_default='admin'))
