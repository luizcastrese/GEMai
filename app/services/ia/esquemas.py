"""Contratos das saídas de IA. Toda resposta de provedor é validada contra estes modelos
e saneada (limites de tamanho) antes de ser gravada: a IA nunca grava diretamente no ERP."""
from typing import Literal

from ...constants import PARAMETROS_TEMPO_OBSOLETOS

from pydantic import BaseModel, Field

from ..modelo_tempo import METODOS_LIGACAO
from ..modulos.catalogo import CHAVES as CHAVES_MODULOS
from ..modulos.catalogo import ChaveModulo

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
    funcao_requerida: str = ""  # mão de obra (ex.: marceneiro, auxiliar)
    num_pessoas: int = 1
    espaco_origem: str | None = None
    espaco_destino: str | None = None
    inicio_marco: str = ""  # quando o apontamento começa (consistência dos parâmetros)
    fim_marco: str = ""


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


class EspacoIA(BaseModel):
    nome: str
    tipo: Literal["area", "posto", "estoque", "expedicao"] = "area"


class MaterialIA(BaseModel):
    nome: str
    unidade_medida: str = "un"


class EstruturaProposta(BaseModel):
    processos: list[ProcessoIA] = Field(default_factory=list)
    recursos: list[RecursoIA] = Field(default_factory=list)
    materiais: list[MaterialIA] = Field(default_factory=list)
    espacos: list[EspacoIA] = Field(default_factory=list)
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
                          for x in op.parametros[:MAX_PARAMS] if _t(x.nome, 80) and _t(x.nome, 80).lower().replace(" ", "_") not in PARAMETROS_TEMPO_OBSOLETOS]
                ops.append(OperacaoIA(
                    nome=_t(op.nome, 200), descricao=_t(op.descricao, 2000), recurso=_t(op.recurso, 200) or None,
                    formula_tipo=op.formula_tipo, unidade_medida=_t(op.unidade_medida, 30) or "un",
                    dados_medidos=[_t(d, 40) for d in op.dados_medidos[:30] if _t(d, 40)], parametros=params,
                    funcao_requerida=_t(op.funcao_requerida, 120), num_pessoas=min(max(op.num_pessoas or 1, 1), 50),
                    espaco_origem=_t(op.espaco_origem, 200) or None, espaco_destino=_t(op.espaco_destino, 200) or None,
                    inicio_marco=_t(op.inicio_marco, 300), fim_marco=_t(op.fim_marco, 300)))
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
        espacos=[EspacoIA(nome=_t(x.nome, 200), tipo=x.tipo) for x in e.espacos[:MAX_LISTA] if _t(x.nome, 200)],
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
    """Um passo do plano = um MÓDULO do catálogo fechado + o mapeamento das condições do produto.

    A IA escolhe o módulo e aponta quais componentes, equipamento e locais entram. NÃO há campo de tempo, taxa,
    percentual ou elemento: o sistema deriva as condições (medidas, pesos, distâncias, ficha técnica) e calcula.
    Campos desconhecidos (ex.: `a_min`, `elementos`, `tempo_min`) são ignorados na validação.
    """

    nome: str
    modulo: ChaveModulo
    grupo: str = ""
    final: bool = False  # montagem final (liga os subconjuntos entre si)
    componentes: list[str] = Field(default_factory=list)
    recurso: str | None = None  # equipamento ou meio de movimentação cadastrado
    espaco_origem: str | None = None
    espaco_destino: str | None = None
    pessoas: int = 1
    observacao: str = ""


class SugestaoModulo(BaseModel):
    """A IA só ESCOLHE um módulo do catálogo fechado (ou nenhum). Sem tempos, taxas ou coeficientes."""

    modulo: ChaveModulo | None = None
    justificativa: str = ""


def sanear_sugestao_modulo(x: SugestaoModulo) -> SugestaoModulo:
    return SugestaoModulo(modulo=x.modulo if x.modulo in CHAVES_MODULOS else None, justificativa=_limpo(x.justificativa, 400))


# ---------------------------------------------------------------- meios: identificação e ficha técnica
class CandidatoMeio(BaseModel):
    marca: str = ""
    modelo: str = ""
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao", "meio_movimentacao"] = "maquina"
    funcao: Literal["", "corte", "furacao", "bordo", "movimentacao", "acabamento", "montagem", "outro"] = ""
    confianca: Literal["baixa", "media", "alta"] = "baixa"
    observacao: str = ""


class IdentificacaoMeio(BaseModel):
    candidatos: list[CandidatoMeio] = Field(default_factory=list)
    pergunta: str | None = None  # só quando a descrição é ambígua


class ParametroFichaIA(BaseModel):
    nome: str
    valor: float | None = None
    unidade: str = ""
    fonte_url: str = ""
    confianca: Literal["baixa", "media", "alta"] = "baixa"


class FichaTecnicaIA(BaseModel):
    """Só números e referência. Nenhum texto de catálogo é aceito ou guardado."""

    encontrada: bool = False
    parametros: list[ParametroFichaIA] = Field(default_factory=list)


def _limpo(s: str | None, n: int) -> str:
    return "".join(c for c in (s or "") if c.isprintable()).strip()[:n]


def sanear_identificacao(i: IdentificacaoMeio) -> IdentificacaoMeio:
    return IdentificacaoMeio(
        candidatos=[CandidatoMeio(marca=_limpo(c.marca, 120), modelo=_limpo(c.modelo, 200), tipo=c.tipo, funcao=c.funcao,
                                  confianca=c.confianca, observacao=_limpo(c.observacao, 300))
                    for c in i.candidatos[:5] if _limpo(c.modelo, 200) or _limpo(c.marca, 120)],
        pergunta=_limpo(i.pergunta, 300) or None)


def sanear_ficha(f: FichaTecnicaIA, funcao: str = "") -> tuple[list[dict], list[dict]]:
    """(parâmetros aceitos, descartados com o motivo). Só entra o que tem nome do catálogo (aplicável à função do meio),
    valor numérico na unidade certa, dentro da faixa plausível e FONTE (URL http/https) citada."""
    from ..modulos import ficha
    aceitos, descartados, vistos = [], [], set()
    for p in f.parametros[:40]:
        nome = _limpo(p.nome, 80)

        def recusa(motivo: str):
            descartados.append({"nome": nome, "motivo": motivo})

        if nome in vistos:
            recusa("duplicado")
            continue
        cat = ficha.PARAMETROS_FICHA.get(nome)
        if cat is None:
            recusa("parâmetro fora do catálogo da ficha técnica")
            continue
        if funcao and funcao not in cat.funcoes:
            recusa("não se aplica à função deste meio")
            continue
        if p.valor is None:
            recusa("sem valor")
            continue
        url = ficha.url_de_fonte(_limpo(p.fonte_url, 500))
        if url is None:
            recusa("sem fonte citada (URL http/https válida): número sem fonte não entra")
            continue
        valor, motivo = ficha.validar_valor(nome, p.valor, _limpo(p.unidade, 20) or cat.unidade)
        if valor is None:
            recusa(motivo)
            continue
        vistos.add(nome)
        aceitos.append({"nome": nome, "valor": valor, "unidade": cat.unidade, "fonte_url": url, "confianca": p.confianca})
    return aceitos, descartados


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
        if ps.modulo not in CHAVES_MODULOS:  # o catálogo é fechado
            continue
        passos.append(PassoIA(
            nome=_t(ps.nome, 300), modulo=ps.modulo, grupo=_t(ps.grupo, 80), final=bool(ps.final),
            componentes=[_t(x, 200) for x in ps.componentes[:60] if _t(x, 200)], recurso=_t(ps.recurso, 200) or None,
            espaco_origem=_t(ps.espaco_origem, 200) or None, espaco_destino=_t(ps.espaco_destino, 200) or None,
            pessoas=min(max(int(ps.pessoas or 1), 1), 20), observacao=_t(ps.observacao, 1000)))
    return PlanoProposta(passos=passos, premissas=[_t(x, 400) for x in p.premissas[:30] if _t(x, 400)],
                         dados_faltantes=[_t(x, 300) for x in p.dados_faltantes[:30] if _t(x, 300)],
                         confianca=p.confianca, justificativa=_t(p.justificativa, 3000))
