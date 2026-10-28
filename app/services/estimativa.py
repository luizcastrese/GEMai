"""Estimativa de tempo por operação (o "tempo planejado" do gêmeo digital).

Prioridade da base de cálculo (sempre explicitada em `fonte`):
1. `historico`  – apontamentos APROVADOS, se houver amostras suficientes. O histórico CALIBRA o modelo de tempo,
                  não o substitui: cada apontamento é levado a tempo normal pelo ritmo de quem o fez (só na parte
                  do tempo que depende do operador), a mediana das amostras é o tempo normal e as tolerâncias do
                  modelo (FT) o transformam em tempo padrão. Sem modelo, não há tolerância a aplicar: o resultado é
                  tempo normal, e isso vem avisado;
2. `parametro`  – parâmetros vigentes e validados por uma pessoa (informados/medidos/calculados);
3. `modelo_ia`  – modelo de tempo (elementos + contorno físico) proposto pela IA e calculado pelo
                  sistema; vem rotulado como validado ou não (`validada`);
4. `sem_base`   – nada disponível ou dados físicos faltando: o sistema não chuta.
Dado medido/validado por pessoa sempre prevalece sobre a estimativa da IA.

Atenção à leitura de planejado × realizado: o "realizado" continua sendo a soma BRUTA dos apontamentos, mas o
planejado `historico` agora é tempo padrão (inclui tolerâncias). O desvio, portanto, deixa de medir só "erro de
estimativa": uma operação feita exatamente no tempo normal aparece com desvio negativo (realizado < padrão).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Apontamento, Ordem, OrdemOperacao, Parametro
from . import modelo_tempo, ritmo, timecalc

DIVERGENCIA_MODELO_HISTORICO = 0.30  # acima disso, avisa que a premissa do modelo provavelmente está errada


@dataclass
class Estimativa:
    prep: float | None
    exec: float | None
    fonte: str
    amostras: int = 0
    avisos: list[str] = field(default_factory=list)
    detalhe: list | None = None  # composição em minutos (elementos do modelo ou, no histórico, normal + tolerâncias)
    validada: bool = True  # False = estimativa da IA ainda não validada por uma pessoa
    # Só preenchidos na fonte `historico` (quantidade pedida, preparação + execução):
    tempo_normal: float | None = None  # antes das tolerâncias
    tolerancia_pct: float | None = None  # p = Σ tolerâncias do modelo, em %; None = sem tolerâncias aplicadas
    ritmo_normalizado: bool = False  # ao menos um apontamento foi levado a tempo normal pelo ritmo da pessoa
    amostras_nao_normalizadas: int = 0  # apontamentos sem pessoa/ritmo conhecido (entram com ritmo 100)

    @property
    def total(self) -> float | None:
        return None if self.exec is None else (self.prep or 0.0) + self.exec


def parametros_vigentes(db: Session, empresa_id: int, escopo_tipo: str, escopo_id: int) -> dict[str, Parametro]:
    rows = db.scalars(select(Parametro).where(
        Parametro.empresa_id == empresa_id, Parametro.escopo_tipo == escopo_tipo,
        Parametro.escopo_id == escopo_id, Parametro.vigente.is_(True),
        Parametro.status_validacao == "validado"))
    return {p.nome: p for p in rows}


# ---------------------------------------------------------------- histórico de apontamentos aprovados
@dataclass(frozen=True)
class Registro:
    """Um apontamento aprovado, não anulado e finalizado (execução ou preparação)."""

    ordem_operacao_id: int
    pessoa_id: int | None
    tipo: str
    duracao_min: float  # bruta
    quantidade: float  # boa + refugo


@dataclass
class Historico:
    plano: dict[int, float]  # ordem_operacao_id -> quantidade planejada
    registros: list[Registro]


def carregar_historico(db: Session, empresa_id: int, operacao_id: int) -> Historico:
    ops = db.execute(
        select(OrdemOperacao.id, OrdemOperacao.qtd_planejada)
        .join(Ordem, Ordem.id == OrdemOperacao.ordem_id)
        .where(OrdemOperacao.empresa_id == empresa_id, OrdemOperacao.operacao_id == operacao_id,
               OrdemOperacao.status == "concluida", Ordem.status != "cancelada")
    ).all()
    if not ops:
        return Historico({}, [])
    plan = {i: q for i, q in ops}
    apts = db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_operacao_id.in_(plan),
        Apontamento.status == "aprovado", Apontamento.anulado.is_(False),
        Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao"))))
    return Historico(plan, [
        Registro(a.ordem_operacao_id, a.pessoa_id, a.tipo, timecalc.duracao_min(a.inicio, a.fim) or 0.0,
                 a.quantidade_boa + a.quantidade_refugo) for a in apts])


def amostras_do_historico(registros: list[Registro], plano: dict[int, float], formula: str,
                          tamanho_lote: float | None,
                          fator: Callable[[Registro], float] | None = None) -> tuple[list[float], list[float]]:
    """(amostras de execução por unidade/lote/execução, amostras de preparação), uma por ordem_operacao.

    `fator` multiplica a duração de CADA apontamento antes de somar por ordem_operacao (normalização pelo
    ritmo de quem executou); sem ele, a duração é a bruta."""
    exec_min: dict[int, float] = {}
    qtd: dict[int, float] = {}
    prep_min: dict[int, float] = {}
    for r in registros:
        d = r.duracao_min * (fator(r) if fator else 1.0)
        if r.tipo == "execucao":
            exec_min[r.ordem_operacao_id] = exec_min.get(r.ordem_operacao_id, 0.0) + d
            qtd[r.ordem_operacao_id] = qtd.get(r.ordem_operacao_id, 0.0) + r.quantidade
        elif r.tipo == "preparacao":
            prep_min[r.ordem_operacao_id] = prep_min.get(r.ordem_operacao_id, 0.0) + d
    amostras = []
    for oo_id, dur in exec_min.items():
        if dur <= 0:
            continue
        if formula == "fixo":
            amostras.append(dur)
        elif formula == "lote":
            lote = tamanho_lote if tamanho_lote and tamanho_lote > 0 else 1.0
            amostras.append(dur / max(math.ceil(plano[oo_id] / lote), 1))
        elif qtd.get(oo_id, 0) > 0:
            amostras.append(dur / qtd[oo_id])
    return amostras, [v for v in prep_min.values() if v > 0]


def historico_operacao(db: Session, empresa_id: int, operacao_id: int, formula: str,
                       tamanho_lote: float | None) -> tuple[list[float], list[float]]:
    """(amostras BRUTAS de execução por unidade/lote/execução, amostras brutas de preparação).

    Duração observada, sem normalizar pelo ritmo nem aplicar tolerâncias. Usada para contar amostras e
    por "Atualizar pelo histórico" (parâmetro); a estimativa usa `_pelo_historico`."""
    h = carregar_historico(db, empresa_id, operacao_id)
    return amostras_do_historico(h.registros, h.plano, formula, tamanho_lote)


def _tolerancias_em_linhas(tolerancias: list[dict], base: float, ft: float) -> list[dict]:
    """Minutos de cada categoria de tolerância (rateio de base·(FT − 1) pelos percentuais), como em `calcular`."""
    total_p = sum(max(float(t.get("percentual", 0)), 0.0) for t in tolerancias) or 1.0
    return [{"nome": f"Tolerância: {t['categoria']} ({float(t['percentual']):g}%)", "tipo": "tolerancia",
             "minutos": round(base * (ft - 1.0) * float(t["percentual"]) / total_p, 3)}
            for t in tolerancias if float(t.get("percentual", 0)) > 0]


def _pelo_historico(db: Session, empresa_id: int, operacao, quantidade: float, produto, recurso, h: Historico,
                    lote: float | None, prep_param: float | None) -> Estimativa:
    """Histórico aprovado → tempo normal (ritmo) → tempo padrão (tolerâncias do modelo).

    Por apontamento: normal = duração · (f · ritmo/100 + (1 − f)), com f a fração do tempo que depende do operador
    (do modelo ativo; sem modelo, f = 1). A normalização é por apontamento porque várias pessoas podem apontar a
    mesma ordem_operacao. Observação: o `ritmo_pct` do próprio modelo continua gerando previsão para aquele ritmo
    (padrão 100) nos caminhos `modelo_ia`/comparação; é decisão consciente, a revisitar.
    """
    s = get_settings()
    avisos: list[str] = []
    m = modelo_tempo.modelo_ativo(db, empresa_id, operacao.id)
    modelo = m if m and (m.status_validacao == "validado" or s.usar_modelo_ia_nao_validado) else None

    # 1) fração do tempo que depende do operador
    f_exec = f_prep = 1.0
    ctx = None
    if modelo is None:
        avisos.append("Sem modelo: assumido 100% do tempo dependente do operador.")
    else:
        ctx = modelo_tempo.montar_contexto(db, empresa_id, operacao, quantidade, produto, recurso)
        fr = modelo_tempo.fracao_operador(modelo.elementos, ctx)
        if fr.geral is None:
            motivo = "; ".join(fr.faltantes) or "modelo sem elementos"
            avisos.append(f"Modelo de tempo incompleto ({motivo}): assumido 100% do tempo dependente do operador.")
        else:
            f_exec = fr.execucao if fr.execucao is not None else fr.geral
            f_prep = fr.preparacao if fr.preparacao is not None else fr.geral

    # 2) ritmo de cada apontamento (pessoa > perfil > 100)
    ritmos = ritmo.ritmos_das_pessoas(db, empresa_id, {r.pessoa_id for r in h.registros if r.pessoa_id})

    def conhecido(r: Registro) -> bool:
        return r.pessoa_id in ritmos and ritmos[r.pessoa_id].conhecido

    def fator(r: Registro) -> float:
        f = f_prep if r.tipo == "preparacao" else f_exec
        return f * (ritmos[r.pessoa_id].valor / 100.0 if conhecido(r) else 1.0) + (1.0 - f)

    usados = [r for r in h.registros if r.duracao_min > 0]
    nao_norm = sum(1 for r in usados if not conhecido(r))
    if nao_norm:
        avisos.append(f"{nao_norm} de {len(usados)} apontamentos sem pessoa/ritmo, não normalizados (ritmo 100).")
    amostras, preps = amostras_do_historico(h.registros, h.plano, operacao.formula_tipo, lote, fator)

    # 3) tempo normal = mediana das amostras normalizadas
    unit_normal = timecalc.mediana(amostras)
    prep_do_historico = len(preps) >= s.min_amostras_historico
    prep_normal = timecalc.mediana(preps) if prep_do_historico else prep_param
    if not prep_do_historico:
        avisos.append("Preparação sem amostras suficientes no histórico: " + (
            "usado o parâmetro validado, sem tolerâncias." if prep_param is not None else "não incluída no tempo."))

    # 4) tolerâncias do modelo → tempo padrão
    tolerancias = list(modelo.tolerancias or []) if modelo else []
    if modelo is not None:
        ft, p = modelo_tempo.fator_tolerancia(tolerancias)
        if modelo.status_validacao != "validado":
            avisos.append("Tolerâncias de um modelo ainda não validado por um gestor.")
    else:
        ft, p = 1.0, None
        avisos.append("Sem tolerâncias: tempo normal, não padrão.")
    unit_padrao = unit_normal * ft
    prep_padrao = prep_normal * ft if prep_do_historico and prep_normal is not None else prep_normal
    prep_n, exec_n = timecalc.estimar(operacao.formula_tipo, quantidade, prep_normal, unit_normal, lote)
    prep_p, exec_p = timecalc.estimar(operacao.formula_tipo, quantidade, prep_padrao, unit_padrao, lote)

    # 5) composição (mesma forma dos elementos do modelo: nome/tipo/minutos)
    detalhe = [{"nome": "Tempo normal — execução (mediana do histórico normalizado pelo ritmo)", "tipo": "normal",
                "minutos": round(exec_n, 3)}]
    if prep_n:
        detalhe.append({"nome": "Tempo normal — preparação", "tipo": "normal", "minutos": round(prep_n, 3)})
    if modelo is not None:
        base_tol = exec_n + (prep_n if prep_do_historico else 0.0)
        detalhe += _tolerancias_em_linhas(tolerancias, base_tol, ft)
        detalhe.append({"nome": f"Tempo padrão (normal × FT {ft:.4f})", "tipo": "padrao",
                        "minutos": round((prep_p or 0.0) + exec_p, 3)})

    # 6) sinal de premissa errada: modelo (ritmo 100) × histórico normalizado
    if modelo is not None and ctx is not None and exec_p:
        previsto = modelo_tempo.calcular(modelo.elementos, modelo.fator_ambiente, ctx, tolerancias, 100.0)
        if previsto.completo and previsto.exec > 0 and abs(previsto.exec - exec_p) / exec_p > DIVERGENCIA_MODELO_HISTORICO:
            avisos.append(f"O modelo de tempo prevê {previsto.exec:.1f} min de execução (ritmo 100) e o histórico "
                          f"normalizado indica {exec_p:.1f} min: revise as premissas do modelo.")

    return Estimativa(
        prep=prep_p, exec=exec_p, fonte="historico", amostras=len(amostras), avisos=avisos, detalhe=detalhe,
        validada=modelo is None or modelo.status_validacao == "validado",
        tempo_normal=round(prep_n + exec_n, 3), tolerancia_pct=None if p is None else round(p * 100.0, 3),
        ritmo_normalizado=len(usados) > nao_norm, amostras_nao_normalizadas=nao_norm)


def estimar_operacao(db: Session, empresa_id: int, operacao, quantidade: float, produto=None, recurso=None) -> Estimativa:
    s = get_settings()
    params = parametros_vigentes(db, empresa_id, "operacao", operacao.id)
    val = lambda n: params[n].valor_num if n in params else None  # noqa: E731
    lote = val("tamanho_lote")
    aviso: list[str] = []
    h = carregar_historico(db, empresa_id, operacao.id)
    # amostras brutas: só decidem se há histórico suficiente (a normalização não muda a contagem)
    amostras, preps = amostras_do_historico(h.registros, h.plano, operacao.formula_tipo, lote)

    if amostras and len(amostras) >= s.min_amostras_historico:
        return _pelo_historico(db, empresa_id, operacao, quantidade, produto, recurso, h, lote,
                               val("tempo_preparacao_min"))
    if val("tempo_unitario_min") is not None:
        # Parâmetro validado por pessoa: comportamento inalterado (tempo informado, sem tolerâncias do modelo).
        if amostras:
            aviso.append(f"Histórico insuficiente ({len(amostras)}/{s.min_amostras_historico} amostras aprovadas).")
        prep = val("tempo_preparacao_min")
        if len(preps) >= s.min_amostras_historico:
            prep = timecalc.mediana(preps)
        p, e = timecalc.estimar(operacao.formula_tipo, quantidade, prep, val("tempo_unitario_min"), lote)
        return Estimativa(prep=p, exec=e, fonte="parametro", amostras=len(amostras), avisos=aviso)

    # sem histórico nem parâmetro: tenta o modelo de tempo (gêmeo digital)
    m = modelo_tempo.modelo_ativo(db, empresa_id, operacao.id)
    if m and (m.status_validacao == "validado" or s.usar_modelo_ia_nao_validado):
        ctx = modelo_tempo.montar_contexto(db, empresa_id, operacao, quantidade, produto, recurso)
        # O ritmo do modelo gera a previsão para ESSE ritmo (padrão 100); não usa o ritmo de ninguém em particular.
        r = modelo_tempo.calcular(m.elementos, m.fator_ambiente, ctx, m.tolerancias, m.ritmo_pct)
        if r.completo:
            if m.status_validacao != "validado":
                aviso.append("Tempo estimado pela IA e ainda não validado por um gestor.")
            prep = r.prep
            if len(preps) >= s.min_amostras_historico:
                prep = timecalc.mediana(preps)
            return Estimativa(prep=prep, exec=r.exec, fonte="modelo_ia", amostras=len(amostras), avisos=aviso,
                              detalhe=r.elementos, validada=m.status_validacao == "validado")
        aviso.append("Modelo de tempo incompleto: " + "; ".join(r.faltantes or ["modelo sem elementos"]))
        return Estimativa(prep=None, exec=None, fonte="sem_base", amostras=len(amostras), avisos=aviso,
                          detalhe=r.elementos, validada=False)
    aviso.append("Sem parâmetro validado, histórico suficiente ou modelo de tempo: tempo não estimado.")
    return Estimativa(prep=None, exec=None, fonte="sem_base", amostras=len(amostras), avisos=aviso)
