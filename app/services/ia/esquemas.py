"""Contratos das saídas de IA. Toda resposta de provedor é validada contra estes modelos
e saneada (limites de tamanho) antes de ser gravada: a IA nunca grava diretamente no ERP."""
from typing import Literal

from pydantic import BaseModel, Field

from ..modelo_tempo import METODOS_LIGACAO, ElementoTempo, sanear_elementos


class PontoInvestigacao(BaseModel):
    titulo: str
    evidencia: str
    hipotese: str = ""


class AnaliseTexto(BaseModel):
    resumo: str
    pontos_investigacao: list[PontoInvestigacao] = Field(default_factory=list)


# ---------------------------------------------------------------- saneamento


def _t(s: str | None, n: int) -> str:
    return (s or "").replace("\x00", "").strip()[:n]


def sanear_analise(a: AnaliseTexto) -> AnaliseTexto:
    return AnaliseTexto(
        resumo=_t(a.resumo, 4000),
        pontos_investigacao=[PontoInvestigacao(titulo=_t(p.titulo, 200), evidencia=_t(p.evidencia, 1000),
                                               hipotese=_t(p.hipotese, 1000))
                             for p in a.pontos_investigacao[:15] if _t(p.titulo, 200)])


# ---------------------------------------------------------------- produto (lista de componentes) e plano de trabalho
class ComponenteIA(BaseModel):
    nome: str
    quantidade: float = 1.0
    material: str = ""
    grupo: str = "Corpo"
    comprimento_m: float | None = None
    largura_m: float | None = None
    espessura_m: float | None = None
    peso_kg: float | None = None
    furos: int = 0
    bordas_m: float | None = None


class LigacaoIA(BaseModel):
    componente: str
    ligado_a: str | None = None
    metodo: str = "parafuso"
    fixadores: int = 0


class EstruturaProdutoIA(BaseModel):
    componentes: list[ComponenteIA] = Field(default_factory=list)
    ligacoes: list[LigacaoIA] = Field(default_factory=list)
    dados_faltantes: list[str] = Field(default_factory=list)
    observacoes: str = ""


class PassoIA(BaseModel):
    nome: str
    tipo: Literal["movimentacao", "corte", "furacao", "bordo", "montagem", "inspecao", "outro"] = "outro"
    grupo: str = ""
    componentes: list[str] = Field(default_factory=list)
    qtd_pecas: float = 1.0
    recurso: str | None = None
    espaco_origem: str | None = None
    espaco_destino: str | None = None
    pessoas: int = 1
    elementos: list[ElementoTempo] = Field(default_factory=list)
    observacao: str = ""


class PlanoProposta(BaseModel):
    passos: list[PassoIA] = Field(default_factory=list)
    premissas: list[str] = Field(default_factory=list)
    dados_faltantes: list[str] = Field(default_factory=list)
    confianca: Literal["baixa", "media", "alta"] = "baixa"
    justificativa: str = ""


def sanear_estrutura_produto(e: EstruturaProdutoIA) -> EstruturaProdutoIA:
    def n(v, lo, hi):
        return None if v is None or v != v else min(max(float(v), lo), hi)
    comps, vistos = [], set()
    for c in e.componentes[:200]:
        nome = _t(c.nome, 200)
        if not nome or nome.lower() in vistos:
            continue
        vistos.add(nome.lower())
        comps.append(ComponenteIA(
            nome=nome, quantidade=n(c.quantidade, 0.01, 10000) or 1.0, material=_t(c.material, 80),
            grupo=_t(c.grupo, 80) or "Corpo", comprimento_m=n(c.comprimento_m, 0.001, 20), largura_m=n(c.largura_m, 0.001, 20),
            espessura_m=n(c.espessura_m, 0.0001, 5), peso_kg=n(c.peso_kg, 0, 100000),
            furos=int(min(max(c.furos or 0, 0), 2000)), bordas_m=n(c.bordas_m, 0, 200)))
    nomes = {c.nome.lower() for c in comps}
    ligs = [LigacaoIA(componente=_t(l.componente, 200), ligado_a=_t(l.ligado_a, 200) or None,
                      metodo=(_t(l.metodo, 30).lower() if _t(l.metodo, 30).lower() in METODOS_LIGACAO else "outro"), fixadores=int(min(max(l.fixadores or 0, 0), 5000)))
            for l in e.ligacoes[:400] if _t(l.componente, 200).lower() in nomes
            and (not _t(l.ligado_a, 200) or _t(l.ligado_a, 200).lower() in nomes)]
    return EstruturaProdutoIA(componentes=comps, ligacoes=ligs, observacoes=_t(e.observacoes, 3000),
                              dados_faltantes=[_t(x, 300) for x in e.dados_faltantes[:30] if _t(x, 300)])


def sanear_plano(p: PlanoProposta) -> PlanoProposta:
    passos = []
    for ps in p.passos[:120]:
        if not _t(ps.nome, 300):
            continue
        els = sanear_elementos(ps.elementos)
        passos.append(PassoIA(
            nome=_t(ps.nome, 300), tipo=ps.tipo, grupo=_t(ps.grupo, 80), componentes=[_t(x, 200) for x in ps.componentes[:60] if _t(x, 200)],
            qtd_pecas=min(max(float(ps.qtd_pecas or 1), 0.01), 1e7), recurso=_t(ps.recurso, 200) or None,
            espaco_origem=_t(ps.espaco_origem, 200) or None, espaco_destino=_t(ps.espaco_destino, 200) or None,
            pessoas=min(max(int(ps.pessoas or 1), 1), 20), elementos=els, observacao=_t(ps.observacao, 1000)))
    return PlanoProposta(passos=passos, premissas=[_t(x, 400) for x in p.premissas[:30] if _t(x, 400)],
                         dados_faltantes=[_t(x, 300) for x in p.dados_faltantes[:30] if _t(x, 300)],
                         confianca=p.confianca, justificativa=_t(p.justificativa, 3000))
