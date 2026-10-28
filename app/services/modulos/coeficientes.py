"""Coeficientes do catálogo de módulos de tempo: valor, unidade, fonte e status.

Nada aqui é "tempo digitado por usuário". São REFERÊNCIAS do próprio catálogo, sempre rotuladas:
- `referencia_generica`: ponto de partida genérico do projeto (confiança baixa), a ser substituído por calibração
  com o histórico da empresa (fator por módulo, validado por uma pessoa);
- `calibrado`: valor ajustado por calibração validada (a calibração é multiplicativa e vive em `calibracao_modulo`).
Os valores iniciais são os que o projeto já usava (`modelo_tempo.REFERENCIAS`, `REFERENCIAS_MONTAGEM`,
`MOVIMENTOS_MOST`). Não foram acrescentados valores novos nem reproduzidas tabelas licenciadas.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import modelo_tempo as mt

GENERICA = "referencia_generica"
CALIBRADO = "calibrado"
VERSAO_CATALOGO = 1


@dataclass(frozen=True)
class Coeficiente:
    chave: str
    valor: float
    unidade: str
    fonte: str
    status: str = GENERICA
    versao: int = 1

    def como_dict(self) -> dict:
        return {"chave": self.chave, "valor": self.valor, "unidade": self.unidade, "fonte": self.fonte,
                "status": self.status, "versao": self.versao}


_PROJ = "Referência genérica do projeto (services/modelo_tempo.REFERENCIAS); substitua por medição/calibração"
_MONT = "Referência genérica de montagem do projeto (services/modelo_tempo.REFERENCIAS_MONTAGEM); calibre com o histórico"
_MOST = ("Índices MOST ILUSTRATIVOS (inspirados no BasicMOST, General Move A B G A B P A); conferir com o cartão "
         "certificado. 1 TMU = 0,0006 min")


def _montar() -> dict[str, Coeficiente]:
    c: dict[str, Coeficiente] = {}

    def add(chave, valor, unidade, fonte):
        c[chave] = Coeficiente(chave, float(valor), unidade, fonte)

    add("velocidade_caminhada_m_min", mt.REFERENCIAS["velocidade_caminhada_m_min"], "m/min", _PROJ)
    add("carga_manual_max_kg", mt.REFERENCIAS["carga_manual_max_kg"], "kg/pessoa", _PROJ)
    add("preparacao_maquina_min", mt.REFERENCIAS["preparacao_maquina_min"], "min", _PROJ)
    add("preparacao_posto_min", mt.REFERENCIAS["preparacao_posto_min"], "min", _PROJ)
    for chave, v in mt.REFERENCIAS_MONTAGEM.items():
        add(chave, v, "min/un" if chave.startswith("fixador:") else "min/unidade do produto", _MONT)
    # pegar e posicionar uma peça (levantar/curvar + posicionar com cuidado), em minutos
    idx = mt.MOVIMENTOS_MOST["levantamento_curvado"] + mt.MOVIMENTOS_MOST["posicionamento_preciso"]
    add("pegar_posicionar_peca_min", sum(idx) * 10 * mt.TMU_MIN, "min/peça", _MOST)
    return c


COEFICIENTES: dict[str, Coeficiente] = _montar()


def coef(chave: str) -> Coeficiente:
    return COEFICIENTES[chave]


def coef_fixador(metodo: str) -> Coeficiente:
    """Coeficiente do método de ligação; método desconhecido cai em `fixador:outro` (declarado, não escondido)."""
    return COEFICIENTES.get(f"fixador:{metodo}") or COEFICIENTES["fixador:outro"]
