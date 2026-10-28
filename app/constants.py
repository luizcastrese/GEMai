"""Vocabulário controlado do sistema (valores gravados no banco)."""

PERFIS = ("admin", "gestor", "operador")

STATUS_ORDEM = ("planejada", "liberada", "em_producao", "parada", "concluida", "cancelada")
ORDEM_ABERTA = ("liberada", "em_producao", "parada")
ORDEM_FINAL = ("concluida", "cancelada")

STATUS_OPERACAO = ("pendente", "em_andamento", "concluida", "pulada")

TIPOS_APONTAMENTO = ("preparacao", "execucao", "espera", "retrabalho")
STATUS_APONTAMENTO = ("registrado", "aprovado", "rejeitado")

TIPOS_OCORRENCIA = ("parada", "retrabalho", "falta_material", "ajuste", "qualidade", "outro")

TIPOS_RECURSO = ("maquina", "posto", "ferramenta", "instalacao")

STATUS_PROCESSO = ("rascunho", "ativo", "substituido", "arquivado")

# Origem do dado (regra principal: separar informado, medido, calculado e sugerido pela IA)
ORIGENS_DADO = ("informado", "medido", "calculado", "ia_sugerido")
STATUS_VALIDACAO = ("pendente", "validado", "rejeitado")

GRUPOS_DIAGNOSTICO = (
    "Processos", "Recursos", "Pessoas", "Materiais", "Tempo", "Quantidade",
    "Qualidade", "Manutenção", "Ergonomia", "Ambiente", "Informação",
)

TIPOS_RECOMENDACAO = (
    "estrutura_processo", "analise_desvio", "analise_gargalo", "relatorio_gestor",
    "indicadores_sugeridos", "processos_semelhantes", "parametro",
)
STATUS_RECOMENDACAO = ("pendente", "aprovada", "aplicada", "rejeitada")

FORMULAS_TEMPO = ("linear", "lote", "fixo")

PARAMETROS_PADRAO = {
    # nome: (unidade, descrição)
    "tamanho_lote": ("un", "Unidades por lote (fórmula 'lote')"),
    "perda_percentual": ("%", "Perda/refugo esperado"),
}

# DEPRECATED: tempo digitado (por unidade/preparação) deixou de ser entrada. O tempo é saída do motor modular
# (histórico normalizado ou módulo do catálogo). Parâmetros antigos seguem gravados, mas são ignorados.
PARAMETROS_TEMPO_OBSOLETOS = ("tempo_preparacao_min", "tempo_unitario_min")
