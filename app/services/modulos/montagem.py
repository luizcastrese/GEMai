"""Módulo `montagem` (por subconjunto ou final): pegar/posicionar as peças e fixar conforme o método de ligação.

Pegar e posicionar usa os índices MOST ilustrativos do catálogo; fixar usa o coeficiente de cada método de ligação
× nº de fixadores. Altura de trabalho e precisão são registradas, mas NÃO alteram o tempo (não há coeficiente com
fonte); o peso define o mínimo de pessoas (carga manual) e alimenta os alertas ergonômicos.
"""
from __future__ import annotations

import math

from .base import EntradaModulo, Modulo, Montagem, ParametroModulo, el
from .coeficientes import coef, coef_fixador


def montar(e: EntradaModulo) -> Montagem:
    m = Montagem()
    grupo = e.extras.get("grupo") or "Corpo"
    final = bool(e.extras.get("final"))
    n_pecas = e.extras.get("n_pecas")
    if n_pecas is None:
        n_pecas = sum(c["qtd"] for c in e.componentes if c.get("comp") and c.get("larg"))
    por_metodo: dict[str, int] = {}
    for l in e.ligacoes:
        por_metodo[l["metodo"]] = por_metodo.get(l["metodo"], 0) + int(l.get("fixadores") or 0)
    m.parametros = {"grupo": grupo, "pecas_por_unidade": n_pecas, "fixadores_por_metodo": por_metodo,
                    "peso_max_kg": e.peso_max_kg, "peso_conjunto_kg": e.extras.get("peso_conjunto_kg"),
                    "altura_trabalho_m": e.extras.get("altura_trabalho_m"), "precisao": e.extras.get("precisao")}
    if not e.ligacoes and (n_pecas or e.componentes):
        m.faltantes.append("como se montam as peças deste passo (método de ligação e nº de fixadores)" if not final
                           else "como os subconjuntos se ligam na montagem final (método e nº de fixadores)")
    if n_pecas:
        c = coef("pegar_posicionar_peca_min")
        m.coeficientes.append(c)
        m.elementos.append(el(f"Pegar e posicionar {n_pecas:g} peça(s)/conjunto(s) por unidade", "manuseio", "fixo", por_unidade=True,
                              a_min=round(n_pecas * c.valor, 4),
                              justificativa=f"≈{c.valor * 60:.0f} s por peça (índices MOST ilustrativos: curvar/levantar + posicionar com cuidado)."))
    for metodo, n in por_metodo.items():
        if n <= 0:
            continue
        c = coef_fixador(metodo)
        m.coeficientes.append(c)
        m.elementos.append(el(f"Fixar com {metodo} ({n} un por unidade)", "processamento", "fixo", por_unidade=True,
                              a_min=round(n * c.valor, 4), justificativa=f"{c.valor:g} min por {metodo} (referência genérica do catálogo)."))
    peso = e.extras.get("peso_conjunto_kg") if final else e.peso_max_kg
    if peso:
        m.pessoas_minimas = max(math.ceil(peso / coef("carga_manual_max_kg").valor), 1)
    m.premissas.append("Altura de trabalho e precisão são registradas, mas não alteram o tempo (sem coeficiente com fonte).")
    return m


MODULO = Modulo(
    chave="montagem", titulo="Montagem", tipo_passo="montagem", unidade_contagem="unidade_produto", versao=1,
    descricao="Montagem de um subconjunto ou final: pegar/posicionar as peças e fixar conforme os métodos de ligação.",
    parametros=(
        ParametroModulo("metodo_ligacao", "—", "Método de ligação de cada fixação", "produto"),
        ParametroModulo("fixadores", "un", "Nº de fixadores por unidade do produto", "produto"),
        ParametroModulo("pecas_por_unidade", "un", "Peças/conjuntos posicionados por unidade", "produto"),
        ParametroModulo("peso_max_kg", "kg", "Peso da peça mais pesada (define pessoas e alertas)", "produto", obrigatorio=False),
        ParametroModulo("altura_trabalho_m", "m", "Altura de trabalho", "ambiente", obrigatorio=False, efeito_no_tempo=False),
        ParametroModulo("precisao", "—", "Exigência de precisão", "produto", obrigatorio=False, efeito_no_tempo=False)),
    montar=montar)
