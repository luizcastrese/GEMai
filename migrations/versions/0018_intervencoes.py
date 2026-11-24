"""intervenções de método (ECRS) registradas para comparar pedidos antes e depois

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-24 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import app.models


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'intervencoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('unidade_id', sa.Integer(), nullable=False),
        sa.Column('produto_id', sa.Integer(), nullable=False),
        sa.Column('plano_id', sa.Integer(), nullable=True),
        sa.Column('modulo', sa.String(length=30), nullable=True),
        sa.Column('principio', sa.String(length=20), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=False),
        sa.Column('criado_por', sa.Integer(), nullable=True),
        sa.Column('criado_em', app.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['criado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id']),
        sa.ForeignKeyConstraint(['plano_id'], ['planos_trabalho.id']),
        sa.ForeignKeyConstraint(['produto_id'], ['produtos.id']),
        sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('intervencoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_intervencoes_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index('ix_intervencao', ['empresa_id', 'produto_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('intervencoes', schema=None) as batch_op:
        batch_op.drop_index('ix_intervencao')
        batch_op.drop_index(batch_op.f('ix_intervencoes_empresa_id'))
    op.drop_table('intervencoes')
