"""Módulos de usinagem: `corte`, `bordo` e `furacao`.

Cada um calcula o TEMPO DE MÁQUINA a partir de medidas do componente e de parâmetros técnicos da FICHA TÉCNICA
validada do equipamento (avanço, velocidade, cabeçotes, curso). Ficha incompleta ⇒ pendência, nunca um valor
padrão. A preparação da máquina usa o coeficiente do catálogo (referência genérica).
Não inclui a alimentação/retirada manual das peças (não há coeficiente com fonte nesta versão) — declarado nas premissas.
"""
from __future__ import annotations

import math

from .base import EntradaModulo, Modulo, Montagem, ParametroModulo, el
from .coeficientes import coef

_NAO_MANUSEIO = "Alimentação e retirada manual das peças não estão no catálogo desta versão (sem coeficiente com fonte)."


def _pecas(e: EntradaModulo, m: Montagem, exige: tuple[str, ...]):
    """[(componente, quantidade total)] com as medidas exigidas; o resto vira pendência."""
    out = []
    for c in e.componentes:
        faltam = [k for k in exige if not c.get(k)]
        if faltam:
            m.faltantes.append(f"faltam {', '.join(faltam)} de '{c['nome']}'")
            continue
        out.append((c, c["qtd"] * e.unidades_produto))
    return out


def _ficha(e: EntradaModulo, m: Montagem, nomes: tuple[str, ...]) -> list[float | None]:
    if not e.recurso_nome:
        m.faltantes.append("falta o equipamento deste passo (cadastre e escolha um meio)")
    vals = []
    for n in nomes:
        v = e.ficha.get(n)
        vals.append(v if v else None)
        if e.recurso_nome and not v:
            m.faltantes.append(f"falta '{n}' na ficha técnica de '{e.recurso_nome}'")
    m.parametros.update({n: v for n, v in zip(nomes, vals)})
    return vals


def _prep(e: EntradaModulo, m: Montagem) -> None:
    c = coef("preparacao_maquina_min")
    m.coeficientes.append(c)
    m.elementos.append(el(f"Preparar {e.recurso_nome or 'o equipamento'}", "preparacao", "fixo", a_min=c.valor,
                          justificativa="Referência genérica de preparação do catálogo; calibre com o histórico."))


def _corte(e: EntradaModulo) -> Montagem:
    m = Montagem()
    pecas = _pecas(e, m, ("comp", "larg"))
    (avanco,) = _ficha(e, m, ("avanco_corte_m_min",))
    metros = sum(2 * (c["comp"] + c["larg"]) * q for c, q in pecas)
    m.parametros.update(pecas=sum(q for _, q in pecas), metros_de_corte=round(metros, 3))
    m.premissas += ["Metros de corte = perímetro de cada peça (não considera cortes compartilhados entre peças: é conservador).",
                    "O avanço da ficha técnica vale para todos os materiais e espessuras do produto.", _NAO_MANUSEIO]
    esp_max = e.ficha.get("espessura_max_corte_mm")
    for c, _ in pecas:
        if esp_max and c.get("esp") and c["esp"] * 1000 > esp_max:
            m.alertas.append(f"'{c['nome']}' tem {c['esp'] * 1000:g} mm de espessura, acima do limite de {esp_max:g} mm da ficha de '{e.recurso_nome}'")
    if e.recurso_nome and avanco and not m.faltantes:
        _prep(e, m)
        m.elementos.append(el(f"Cortar em {e.recurso_nome}", "processamento", "fixo", a_min=metros / avanco, depende_operador=False,
                              justificativa=f"{metros:g} m de corte a {avanco:g} m/min (ficha técnica)."))
    return m


def _bordo(e: EntradaModulo) -> Montagem:
    m = Montagem()
    pecas = [(c, q) for c, q in _pecas(e, m, ("bordas_m",))]
    (vel,) = _ficha(e, m, ("velocidade_bordo_m_min",))
    metros = sum(c["bordas_m"] * q for c, q in pecas)
    m.parametros.update(pecas=sum(q for _, q in pecas), metros_de_borda=round(metros, 3))
    m.premissas += ["A velocidade de alimentação da ficha técnica vale para todos os materiais de borda.", _NAO_MANUSEIO]
    if e.recurso_nome and vel and not m.faltantes:
        _prep(e, m)
        m.elementos.append(el(f"Colar borda em {e.recurso_nome}", "processamento", "fixo", a_min=metros / vel, depende_operador=False,
                              justificativa=f"{metros:g} m de borda a {vel:g} m/min (ficha técnica)."))
    return m


def _furacao(e: EntradaModulo) -> Montagem:
    m = Montagem()
    pecas = _pecas(e, m, ("furos",))
    cab, curso, avanco = _ficha(e, m, ("cabecotes_furacao", "curso_furacao_mm", "avanco_furacao_mm_min"))
    furos = sum(c["furos"] * q for c, q in pecas)
    m.parametros.update(pecas=sum(q for _, q in pecas), furos=furos)
    m.premissas += ["Um ciclo de furação por grupo de cabeçotes: tempo do ciclo = curso ÷ avanço (ficha técnica).", _NAO_MANUSEIO]
    if e.recurso_nome and cab and curso and avanco and not m.faltantes:
        ciclos = sum(math.ceil(c["furos"] / cab) * q for c, q in pecas)
        m.parametros["ciclos"] = ciclos
        _prep(e, m)
        m.elementos.append(el(f"Furar em {e.recurso_nome}", "processamento", "fixo", a_min=ciclos * curso / avanco, depende_operador=False,
                              justificativa=f"{ciclos:g} ciclo(s) de {curso:g} mm a {avanco:g} mm/min, {cab:g} cabeçote(s) (ficha técnica)."))
    return m


_P_PECAS = ParametroModulo("pecas", "un", "Nº de peças do passo", "produto")

CORTE = Modulo(
    chave="corte", titulo="Corte", tipo_passo="corte", unidade_contagem="peca", precisa_recurso=True, versao=1,
    descricao="Corte de painéis em equipamento cadastrado (tempo de máquina = metros de corte ÷ avanço).",
    parametros=(_P_PECAS, ParametroModulo("comp", "m", "Comprimento das peças", "produto"),
                ParametroModulo("larg", "m", "Largura das peças", "produto"),
                ParametroModulo("esp", "m", "Espessura (confere o limite do equipamento)", "produto", obrigatorio=False, efeito_no_tempo=False),
                ParametroModulo("avanco_corte_m_min", "m/min", "Avanço de corte (ficha técnica)", "meio")), montar=_corte)
BORDO = Modulo(
    chave="bordo", titulo="Colagem de borda", tipo_passo="bordo", unidade_contagem="peca", precisa_recurso=True, versao=1,
    descricao="Colagem de borda em coladeira cadastrada (tempo de máquina = metros de borda ÷ velocidade).",
    parametros=(_P_PECAS, ParametroModulo("bordas_m", "m", "Metros de borda por peça", "produto"),
                ParametroModulo("velocidade_bordo_m_min", "m/min", "Velocidade de alimentação (ficha técnica)", "meio")), montar=_bordo)
FURACAO = Modulo(
    chave="furacao", titulo="Furação", tipo_passo="furacao", unidade_contagem="peca", precisa_recurso=True, versao=1,
    descricao="Furação em furadeira cadastrada (ciclos = furos ÷ cabeçotes; tempo do ciclo = curso ÷ avanço).",
    parametros=(_P_PECAS, ParametroModulo("furos", "un", "Furos por peça", "produto"),
                ParametroModulo("cabecotes_furacao", "un", "Cabeçotes (ficha técnica)", "meio"),
                ParametroModulo("curso_furacao_mm", "mm", "Curso do ciclo (ficha técnica)", "meio"),
                ParametroModulo("avanco_furacao_mm_min", "mm/min", "Avanço (ficha técnica)", "meio")), montar=_furacao)
