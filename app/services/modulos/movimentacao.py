"""Módulo `movimentacao`: levar peças de um local a outro.

Condições: distância entre os locais, peso da peça mais pesada, nº de pessoas, piso e MEIO DE MOVIMENTAÇÃO.
- Com meio cadastrado: velocidade e capacidade de carga vêm da FICHA TÉCNICA validada do meio; falta ⇒ pendência.
- Sem meio: pessoa carregando (velocidade de caminhada e carga manual por pessoa do catálogo, referências genéricas).
"""
from __future__ import annotations

import math

from .base import EntradaModulo, Modulo, Montagem, ParametroModulo, el
from .coeficientes import coef


def montar(e: EntradaModulo) -> Montagem:
    m = Montagem()
    peso = e.peso_max_kg  # a peça mais pesada define o mínimo de pessoas e a capacidade; o peso médio, quantas cabem por viagem
    medio = e.peso_medio_kg or peso
    de, para = e.origem_nome or "origem", e.destino_nome or "destino"
    if e.distancia_m is None:
        m.faltantes.append(f"falta a distância entre {de} e {para}")
    if peso is None:
        m.faltantes.append("falta o peso das peças (informe o peso, ou o material e a espessura)")
    m.parametros = {"distancia_m": e.distancia_m, "peso_max_kg": peso, "peso_medio_kg": round(medio, 3) if medio else None, "pessoas": e.pessoas, "piso": e.piso or None,
                    "meio": e.meio_nome}
    if e.piso:
        m.premissas.append(f"O piso ('{e.piso}') é registrado, mas não altera o tempo: não há coeficiente com fonte para isso.")
    if e.meio_nome:
        vel, cap = e.ficha_meio.get("velocidade_meio_m_min"), e.ficha_meio.get("capacidade_carga_kg")
        if not vel:
            m.faltantes.append(f"falta a velocidade do meio '{e.meio_nome}' (ficha técnica)")
        if not cap:
            m.faltantes.append(f"falta a capacidade de carga do meio '{e.meio_nome}' (ficha técnica)")
        m.parametros.update(velocidade_m_min=vel, capacidade_carga_kg=cap)
        if vel and cap and peso:
            if peso > cap:
                m.faltantes.append(f"a peça mais pesada ({peso:g} kg) passa da capacidade do meio '{e.meio_nome}' ({cap:g} kg)")
                return m
            itens = max(int(cap // medio), 1)
        else:
            return m
    else:
        c_vel, c_carga = coef("velocidade_caminhada_m_min"), coef("carga_manual_max_kg")
        m.coeficientes += [c_vel, c_carga]
        vel = c_vel.valor
        if peso is None:
            return m
        m.pessoas_minimas = max(math.ceil(peso / c_carga.valor), 1)
        itens = max(int(c_carga.valor * max(e.pessoas, m.pessoas_minimas) // medio), 1)
        m.premissas.append(f"Sem meio de movimentação cadastrado: pessoa carregando, a {vel:g} m/min e até {c_carga.valor:g} kg por pessoa "
                           "(referências genéricas do catálogo). Cadastre um meio para o plano usá-lo.")
    m.parametros["itens_por_viagem"] = itens
    if e.distancia_m is None or not vel:
        return m
    m.elementos.append(el(f"Levar de {de} até {para}", "deslocamento", "deslocamento", velocidade_m_min=vel,
                          itens_por_viagem=float(itens), ida_e_volta=True,
                          justificativa=f"{itens} peça(s) por viagem" + (f" no meio '{e.meio_nome}'." if e.meio_nome else
                                                                   f" (carga manual de referência de {coef('carga_manual_max_kg').valor:g} kg por pessoa).")))
    return m


MODULO = Modulo(
    chave="movimentacao", titulo="Movimentação de peças", tipo_passo="movimentacao", unidade_contagem="peca", versao=1,
    descricao="Leva peças entre dois locais cadastrados, a pé ou com um meio de movimentação.",
    parametros=(
        ParametroModulo("distancia_m", "m", "Distância entre os locais de origem e destino", "ambiente"),
        ParametroModulo("peso_max_kg", "kg", "Peso da peça mais pesada (mínimo de pessoas e capacidade do meio)", "produto"),
        ParametroModulo("peso_medio_kg", "kg", "Peso médio das peças (quantas cabem por viagem)", "produto"),
        ParametroModulo("pessoas", "un", "Pessoas no transporte", "pedido", obrigatorio=False),
        ParametroModulo("meio", "—", "Meio de movimentação (carrinho, empilhadeira…)", "meio", obrigatorio=False),
        ParametroModulo("velocidade_meio_m_min", "m/min", "Velocidade do meio (ficha técnica)", "meio", obrigatorio=False),
        ParametroModulo("capacidade_carga_kg", "kg", "Capacidade de carga do meio (ficha técnica)", "meio", obrigatorio=False),
        ParametroModulo("piso", "—", "Tipo de piso", "ambiente", obrigatorio=False, efeito_no_tempo=False)),
    montar=montar)
