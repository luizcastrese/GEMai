"""calibração por módulo: vínculo da ordem com o módulo/passo e tabela de fatores

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import app.models


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('plano_passos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('previsto_normal_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('fracao_operador', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('fator_calibracao', sa.Float(), nullable=False, server_default='1.0'))
        batch_op.add_column(sa.Column('amostras_calibracao', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('ordem_operacoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plano_passo_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('modulo', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('previsto_normal_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('fracao_operador', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('fator_calibracao', sa.Float(), nullable=False, server_default='1.0'))
        batch_op.create_foreign_key('fk_oo_plano_passo', 'plano_passos', ['plano_passo_id'], ['id'])
    op.create_table('calibracoes_modulo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('modulo', sa.String(length=30), nullable=False),
    sa.Column('fator', sa.Float(), nullable=False),
    sa.Column('mediana_bruta', sa.Float(), nullable=False),
    sa.Column('limitado', sa.Boolean(), nullable=False),
    sa.Column('amostras', sa.Integer(), nullable=False),
    sa.Column('versao', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('vigente', sa.Boolean(), nullable=False),
    sa.Column('justificativa', sa.Text(), nullable=False),
    sa.Column('criado_por', sa.Integer(), nullable=True),
    sa.Column('criado_em', app.models.UTCDateTime(), nullable=False),
    sa.Column('validado_por', sa.Integer(), nullable=True),
    sa.Column('validado_em', app.models.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['criado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.ForeignKeyConstraint(['validado_por'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('calibracoes_modulo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calibracoes_modulo_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index('ix_calib_modulo', ['empresa_id', 'unidade_id', 'modulo'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('calibracoes_modulo', schema=None) as batch_op:
        batch_op.drop_index('ix_calib_modulo')
        batch_op.drop_index(batch_op.f('ix_calibracoes_modulo_empresa_id'))
    op.drop_table('calibracoes_modulo')
    with op.batch_alter_table('ordem_operacoes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_oo_plano_passo', type_='foreignkey')
        batch_op.drop_column('fator_calibracao')
        batch_op.drop_column('fracao_operador')
        batch_op.drop_column('previsto_normal_min')
        batch_op.drop_column('modulo')
        batch_op.drop_column('plano_passo_id')
    with op.batch_alter_table('plano_passos', schema=None) as batch_op:
        batch_op.drop_column('amostras_calibracao')
        batch_op.drop_column('fator_calibracao')
        batch_op.drop_column('fracao_operador')
        batch_op.drop_column('previsto_normal_min')
