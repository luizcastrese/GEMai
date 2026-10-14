"""remove o fluxo antigo: diagnóstico, processos, operações, parâmetros e modelo de tempo por operação

DESTRUTIVA e sem volta: os dados dessas tabelas (e as colunas que apontavam para elas) são apagados.
Faça backup antes de aplicar. Ordens, apontamentos, planos, produtos e cadastros são preservados.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14 22:00:00.000000
"""
from alembic import op


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

COLUNAS = {
    'ordens': ['processo_id'],
    'ordem_operacoes': ['operacao_id', 'opcional', 'formula_tipo', 'amostras', 'estimativa_validada'],
    'apontamentos': ['dados_extras'],
    'recursos': ['processos_relacionados'],
    'unidades': ['descricao_operacao', 'objetivo', 'principais_problemas', 'informacoes_disponiveis'],
}
TABELAS = ['modelos_tempo', 'parametros', 'operacoes', 'etapas', 'processos', 'diagnostico_perguntas']


def upgrade() -> None:
    # primeiro as colunas que apontam para as tabelas antigas (FKs), depois as tabelas, dos filhos para os pais
    for tabela, colunas in COLUNAS.items():
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            for c in colunas:
                batch_op.drop_column(c)
    for t in TABELAS:
        op.drop_table(t)


def downgrade() -> None:
    raise NotImplementedError("Migração destrutiva: restaure o backup anterior à 0009 para voltar ao fluxo antigo.")
