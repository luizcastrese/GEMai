"""produto plano de trabalho

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 13:54:13.518291
"""
from alembic import op
import sqlalchemy as sa
import app.models


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('referencias_tempo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('chave', sa.String(length=60), nullable=False),
    sa.Column('minutos', sa.Float(), nullable=False),
    sa.Column('atualizado_em', app.models.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('empresa_id', 'chave')
    )
    with op.batch_alter_table('referencias_tempo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_referencias_tempo_empresa_id'), ['empresa_id'], unique=False)

    op.create_table('componentes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('produto_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('quantidade', sa.Float(), nullable=False),
    sa.Column('material', sa.String(length=80), nullable=False),
    sa.Column('grupo', sa.String(length=80), nullable=False),
    sa.Column('comprimento_m', sa.Float(), nullable=True),
    sa.Column('largura_m', sa.Float(), nullable=True),
    sa.Column('espessura_m', sa.Float(), nullable=True),
    sa.Column('peso_kg', sa.Float(), nullable=True),
    sa.Column('furos', sa.Integer(), nullable=False),
    sa.Column('bordas_m', sa.Float(), nullable=True),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['produto_id'], ['produtos.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('produto_id', 'nome')
    )
    with op.batch_alter_table('componentes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_componentes_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_componentes_produto_id'), ['produto_id'], unique=False)

    op.create_table('planos_trabalho',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('produto_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=300), nullable=False),
    sa.Column('quantidade', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('provedor', sa.String(length=80), nullable=False),
    sa.Column('confianca', sa.String(length=10), nullable=False),
    sa.Column('premissas', sa.JSON(), nullable=False),
    sa.Column('faltantes', sa.JSON(), nullable=False),
    sa.Column('alertas', sa.JSON(), nullable=False),
    sa.Column('totais', sa.JSON(), nullable=False),
    sa.Column('ordem_id', sa.Integer(), nullable=True),
    sa.Column('criado_por', sa.Integer(), nullable=True),
    sa.Column('criado_em', app.models.UTCDateTime(), nullable=False),
    sa.Column('confirmado_por', sa.Integer(), nullable=True),
    sa.Column('confirmado_em', app.models.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['confirmado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['criado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['produto_id'], ['produtos.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('planos_trabalho', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_planos_trabalho_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_planos_trabalho_unidade_id'), ['unidade_id'], unique=False)

    op.create_table('ligacoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('produto_id', sa.Integer(), nullable=False),
    sa.Column('componente_id', sa.Integer(), nullable=False),
    sa.Column('ligado_a_id', sa.Integer(), nullable=True),
    sa.Column('metodo', sa.String(length=30), nullable=False),
    sa.Column('fixadores', sa.Integer(), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['componente_id'], ['componentes.id'], ),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['ligado_a_id'], ['componentes.id'], ),
    sa.ForeignKeyConstraint(['produto_id'], ['produtos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ligacoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ligacoes_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ligacoes_produto_id'), ['produto_id'], unique=False)

    op.create_table('plano_passos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('plano_id', sa.Integer(), nullable=False),
    sa.Column('sequencia', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=300), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('grupo', sa.String(length=80), nullable=False),
    sa.Column('componentes', sa.JSON(), nullable=False),
    sa.Column('qtd_pecas', sa.Float(), nullable=False),
    sa.Column('recurso_id', sa.Integer(), nullable=True),
    sa.Column('espaco_origem_id', sa.Integer(), nullable=True),
    sa.Column('espaco_destino_id', sa.Integer(), nullable=True),
    sa.Column('pessoas', sa.Integer(), nullable=False),
    sa.Column('elementos', sa.JSON(), nullable=False),
    sa.Column('tolerancias', sa.JSON(), nullable=False),
    sa.Column('ritmo_pct', sa.Float(), nullable=False),
    sa.Column('composicao', sa.JSON(), nullable=False),
    sa.Column('tempo_prep_min', sa.Float(), nullable=True),
    sa.Column('tempo_exec_min', sa.Float(), nullable=True),
    sa.Column('tempo_padrao_min', sa.Float(), nullable=True),
    sa.Column('tempo_agendado_min', sa.Float(), nullable=True),
    sa.Column('faltantes', sa.JSON(), nullable=False),
    sa.Column('alertas', sa.JSON(), nullable=False),
    sa.Column('observacao', sa.Text(), nullable=False),
    sa.Column('inicio_prev', app.models.UTCDateTime(), nullable=True),
    sa.Column('fim_prev', app.models.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['espaco_destino_id'], ['espacos.id'], ),
    sa.ForeignKeyConstraint(['espaco_origem_id'], ['espacos.id'], ),
    sa.ForeignKeyConstraint(['plano_id'], ['planos_trabalho.id'], ),
    sa.ForeignKeyConstraint(['recurso_id'], ['recursos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plano_passos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plano_passos_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_plano_passos_plano_id'), ['plano_id'], unique=False)

    with op.batch_alter_table('espacos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tolerancia_ambiente_pct', sa.Float(), nullable=True))

    with op.batch_alter_table('ordens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plano_id', sa.Integer(), nullable=True))
        batch_op.alter_column('processo_id',
               existing_type=sa.INTEGER(),
               nullable=True)
        batch_op.create_foreign_key('fk_ordens_plano_id', 'planos_trabalho', ['plano_id'], ['id'])

    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('funcao', sa.String(length=20), nullable=False, server_default=''))



def downgrade() -> None:
    # Ordens geradas por plano não têm processo: não há como representá-las no esquema anterior.
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM ordens WHERE processo_id IS NULL")).scalar():
        raise RuntimeError("Existem ordens geradas por plano de trabalho (sem processo). Cancele/exporte e remova-as antes de reverter.")
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.drop_column('funcao')

    with op.batch_alter_table('ordens', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ordens_plano_id', type_='foreignkey')
        batch_op.alter_column('processo_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_column('plano_id')

    with op.batch_alter_table('espacos', schema=None) as batch_op:
        batch_op.drop_column('tolerancia_ambiente_pct')

    with op.batch_alter_table('plano_passos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plano_passos_plano_id'))
        batch_op.drop_index(batch_op.f('ix_plano_passos_empresa_id'))

    op.drop_table('plano_passos')
    with op.batch_alter_table('ligacoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ligacoes_produto_id'))
        batch_op.drop_index(batch_op.f('ix_ligacoes_empresa_id'))

    op.drop_table('ligacoes')
    with op.batch_alter_table('planos_trabalho', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_planos_trabalho_unidade_id'))
        batch_op.drop_index(batch_op.f('ix_planos_trabalho_empresa_id'))

    op.drop_table('planos_trabalho')
    with op.batch_alter_table('componentes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_componentes_produto_id'))
        batch_op.drop_index(batch_op.f('ix_componentes_empresa_id'))

    op.drop_table('componentes')
    with op.batch_alter_table('referencias_tempo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_referencias_tempo_empresa_id'))

    op.drop_table('referencias_tempo')
