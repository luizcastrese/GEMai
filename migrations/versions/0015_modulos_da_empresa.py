"""módulos de tempo criados pela empresa (arquétipos genéricos) e atributos livres das peças

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-18 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from app.models import UTCDateTime


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'modulos_empresa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('chave', sa.String(length=30), nullable=False),
        sa.Column('titulo', sa.String(length=120), nullable=False),
        sa.Column('arquetipo', sa.String(length=30), nullable=False),
        sa.Column('espec', sa.JSON(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('vigente', sa.Boolean(), nullable=False),
        sa.Column('origem', sa.String(length=20), nullable=False),
        sa.Column('provedor', sa.String(length=80), nullable=False),
        sa.Column('justificativa', sa.Text(), nullable=False),
        sa.Column('criado_por', sa.Integer(), nullable=True),
        sa.Column('criado_em', UTCDateTime(), nullable=False),
        sa.Column('validado_por', sa.Integer(), nullable=True),
        sa.Column('validado_em', UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(['criado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id']),
        sa.ForeignKeyConstraint(['validado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id', 'chave', 'versao'),
    )
    with op.batch_alter_table('modulos_empresa', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_modulos_empresa_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index('ix_modulo_empresa', ['empresa_id', 'chave'], unique=False)
    with op.batch_alter_table('componentes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('atributos', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('componentes', schema=None) as batch_op:
        batch_op.drop_column('atributos')
    with op.batch_alter_table('modulos_empresa', schema=None) as batch_op:
        batch_op.drop_index('ix_modulo_empresa')
        batch_op.drop_index(batch_op.f('ix_modulos_empresa_empresa_id'))
    op.drop_table('modulos_empresa')
