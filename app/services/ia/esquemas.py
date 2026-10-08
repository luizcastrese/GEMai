"""Contratos das saídas de IA. Toda resposta de provedor é validada contra estes modelos
e saneada (limites de tamanho) antes de ser gravada: a IA nunca grava diretamente no ERP."""
from typing import Literal

from pydantic import BaseModel, Field

GRUPOS = ["Processos", "Recursos", "Pessoas", "Materiais", "Tempo", "Quantidade",
          "Qualidade", "Manutenção", "Ergonomia", "Ambiente", "Informação"]


class PerguntaIA(BaseModel):
    grupo: str
    texto: str


class ListaPerguntas(BaseModel):
    perguntas: list[PerguntaIA]


class ParametroIA(BaseModel):
    nome: str
    unidade: str = ""
    valor: float | None = None  # só preencher se o texto da empresa informar o valor
    justificativa: str = ""


class OperacaoIA(BaseModel):
    nome: str
    descricao: str = ""
    recurso: str | None = None
    formula_tipo: Literal["linear", "lote", "fixo"] = "linear"
    unidade_medida: str = "un"
    dados_medidos: list[str] = Field(default_factory=lambda: ["tempo", "quantidade"])
    parametros: list[ParametroIA] = Field(default_factory=list)


class EtapaIA(BaseModel):
    nome: str
    descricao: str = ""
    entradas: list[str] = Field(default_factory=list)
    saidas: list[str] = Field(default_factory=list)
    opcional: bool = False
    condicao: str = ""
    operacoes: list[OperacaoIA] = Field(default_factory=list)


class ProcessoIA(BaseModel):
    nome: str
    macroprocesso: str = ""
    descricao: str = ""
    etapas: list[EtapaIA] = Field(default_factory=list)


class RecursoIA(BaseModel):
    nome: str
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao"] = "maquina"


class MaterialIA(BaseModel):
    nome: str
    unidade_medida: str = "un"


class EstruturaProposta(BaseModel):
    processos: list[ProcessoIA] = Field(default_factory=list)
    recursos: list[RecursoIA] = Field(default_factory=list)
    materiais: list[MaterialIA] = Field(default_factory=list)
    indicadores_sugeridos: list[str] = Field(default_factory=list)
    etapas_possivelmente_omitidas: list[str] = Field(default_factory=list)
    perguntas_pendentes: list[str] = Field(default_factory=list)
    observacoes: str = ""


class PontoInvestigacao(BaseModel):
    titulo: str
    evidencia: str
    hipotese: str = ""


class AnaliseTexto(BaseModel):
    resumo: str
    pontos_investigacao: list[PontoInvestigacao] = Field(default_factory=list)
    indicadores_sugeridos: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- saneamento
MAX_PROCESSOS, MAX_ETAPAS, MAX_OPS, MAX_PARAMS, MAX_LISTA = 10, 40, 10, 10, 60


def _t(s: str | None, n: int) -> str:
    return (s or "").replace("\x00", "").strip()[:n]


def sanear_estrutura(e: EstruturaProposta) -> EstruturaProposta:
    """Aplica limites de tamanho e remove itens vazios."""
    procs = []
    for p in e.processos[:MAX_PROCESSOS]:
        etapas = []
        for et in p.etapas[:MAX_ETAPAS]:
            if not _t(et.nome, 200):
                continue
            ops = []
            for op in et.operacoes[:MAX_OPS]:
                if not _t(op.nome, 200):
                    continue
                params = [ParametroIA(nome=_t(x.nome, 80).lower().replace(" ", "_"), unidade=_t(x.unidade, 30),
                                      valor=x.valor, justificativa=_t(x.justificativa, 500))
                          for x in op.parametros[:MAX_PARAMS] if _t(x.nome, 80)]
                ops.append(OperacaoIA(
                    nome=_t(op.nome, 200), descricao=_t(op.descricao, 2000), recurso=_t(op.recurso, 200) or None,
                    formula_tipo=op.formula_tipo, unidade_medida=_t(op.unidade_medida, 30) or "un",
                    dados_medidos=[_t(d, 40) for d in op.dados_medidos[:30] if _t(d, 40)], parametros=params))
            etapas.append(EtapaIA(
                nome=_t(et.nome, 200), descricao=_t(et.descricao, 2000),
                entradas=[_t(x, 300) for x in et.entradas[:50] if _t(x, 300)],
                saidas=[_t(x, 300) for x in et.saidas[:50] if _t(x, 300)],
                opcional=et.opcional, condicao=_t(et.condicao, 300), operacoes=ops))
        if _t(p.nome, 200):
            procs.append(ProcessoIA(nome=_t(p.nome, 200), macroprocesso=_t(p.macroprocesso, 200),
                                    descricao=_t(p.descricao, 2000), etapas=etapas))
    return EstruturaProposta(
        processos=procs,
        recursos=[RecursoIA(nome=_t(r.nome, 200), tipo=r.tipo) for r in e.recursos[:MAX_LISTA] if _t(r.nome, 200)],
        materiais=[MaterialIA(nome=_t(m.nome, 200), unidade_medida=_t(m.unidade_medida, 30) or "un")
                   for m in e.materiais[:MAX_LISTA] if _t(m.nome, 200)],
        indicadores_sugeridos=[_t(x, 300) for x in e.indicadores_sugeridos[:30] if _t(x, 300)],
        etapas_possivelmente_omitidas=[_t(x, 300) for x in e.etapas_possivelmente_omitidas[:30] if _t(x, 300)],
        perguntas_pendentes=[_t(x, 500) for x in e.perguntas_pendentes[:30] if _t(x, 500)],
        observacoes=_t(e.observacoes, 3000))


def sanear_perguntas(lista: ListaPerguntas, max_n: int = 12) -> list[PerguntaIA]:
    out = []
    for p in lista.perguntas:
        g = p.grupo if p.grupo in GRUPOS else "Processos"
        t = _t(p.texto, 500)
        if t:
            out.append(PerguntaIA(grupo=g, texto=t))
    return out[:max_n]


def sanear_analise(a: AnaliseTexto) -> AnaliseTexto:
    return AnaliseTexto(
        resumo=_t(a.resumo, 4000),
        pontos_investigacao=[PontoInvestigacao(titulo=_t(p.titulo, 200), evidencia=_t(p.evidencia, 1000),
                                               hipotese=_t(p.hipotese, 1000))
                             for p in a.pontos_investigacao[:15] if _t(p.titulo, 200)],
        indicadores_sugeridos=[_t(x, 300) for x in a.indicadores_sugeridos[:20] if _t(x, 300)])
