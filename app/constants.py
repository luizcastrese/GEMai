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

TIPOS_RECOMENDACAO = ("analise_desvio", "analise_gargalo", "relatorio_gestor")
STATUS_RECOMENDACAO = ("pendente", "aprovada", "rejeitada")
