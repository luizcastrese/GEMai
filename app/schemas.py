"""Esquemas de entrada/saída da API (validação rígida na borda)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


def _utc(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


UTC = Annotated[datetime, AfterValidator(_utc)]
Nome = Annotated[str, Field(min_length=1, max_length=200)]
Texto = Annotated[str, Field(max_length=5000)]
Curto = Annotated[str, Field(max_length=300)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth
class RegistrarEmpresaIn(In):
    empresa_nome: Nome
    segmento: Annotated[str, Field(max_length=120)] = ""
    unidade_nome: Nome
    nome: Nome
    email: EmailStr
    senha: Annotated[str, Field(max_length=128)]


class LoginIn(In):
    email: EmailStr
    senha: Annotated[str, Field(max_length=128)]


class UsuarioOut(Out):
    id: int
    empresa_id: int
    nome: str
    email: str
    perfil: str
    ativo: bool
    unidade_ids: list[int] = []


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioOut


class UsuarioIn(In):
    nome: Nome
    email: EmailStr
    senha: Annotated[str, Field(max_length=128)]
    perfil: Literal["admin", "gestor", "operador"]
    unidade_ids: list[int] = []


class UsuarioUpdate(In):
    nome: Nome | None = None
    perfil: Literal["admin", "gestor", "operador"] | None = None
    ativo: bool | None = None
    unidade_ids: list[int] | None = None


class AlterarSenhaIn(In):
    senha_atual: Annotated[str, Field(max_length=128)]
    nova_senha: Annotated[str, Field(max_length=128)]


class RedefinirSenhaIn(In):
    nova_senha: Annotated[str, Field(max_length=128)]


# ------------------------------------------------------------------ empresa / unidade
class EmpresaOut(Out):
    id: int
    nome: str
    segmento: str
    documento: str | None
    fuso: str
    permite_ia_externa: bool
    ia_disponivel: bool = False
    ia_provedor_ativo: str = "heuristica"


class EmpresaUpdate(In):
    nome: Nome | None = None
    segmento: Annotated[str, Field(max_length=120)] | None = None
    documento: Annotated[str, Field(max_length=32)] | None = None
    fuso: Annotated[str, Field(max_length=64)] | None = None
    permite_ia_externa: bool | None = None


class UnidadeIn(In):
    nome: Nome
    descricao_operacao: Texto = ""
    objetivo: Texto = ""
    principais_problemas: Texto = ""
    informacoes_disponiveis: Texto = ""


class UnidadeUpdate(In):
    nome: Nome | None = None
    descricao_operacao: Texto | None = None
    objetivo: Texto | None = None
    principais_problemas: Texto | None = None
    informacoes_disponiveis: Texto | None = None
    ativa: bool | None = None


class UnidadeOut(Out):
    id: int
    nome: str
    descricao_operacao: str
    objetivo: str
    principais_problemas: str
    informacoes_disponiveis: str
    ativa: bool


# ------------------------------------------------------------------ diagnóstico
class PerguntaOut(Out):
    id: int
    unidade_id: int
    grupo: str
    texto: str
    resposta: str | None
    ordem: int
    origem: str


class RespostaIn(In):
    resposta: Annotated[str, Field(max_length=5000)]


# ------------------------------------------------------------------ processos
class CampoExtra(In):
    nome: Annotated[str, Field(min_length=1, max_length=60)]
    tipo: Literal["numero", "texto", "booleano"] = "numero"
    unidade: Annotated[str, Field(max_length=20)] = ""
    obrigatorio: bool = False


Nivel = Literal["baixo", "medio", "alto"]


class Ergonomia(In):
    repetitividade: Nivel | None = None
    esforco_fisico: Nivel | None = None
    postura: Nivel | None = None
    deslocamento: Nivel | None = None
    tempo_em_pe: Nivel | None = None
    pausas: Literal["adequadas", "insuficientes"] | None = None
    condicoes_posto: Annotated[str, Field(max_length=500)] | None = None


class ProcessoIn(In):
    unidade_id: int
    nome: Nome
    macroprocesso: Annotated[str, Field(max_length=200)] = ""
    descricao: Texto = ""
    responsavel_id: int | None = None


class ProcessoUpdate(In):
    nome: Nome | None = None
    macroprocesso: Annotated[str, Field(max_length=200)] | None = None
    descricao: Texto | None = None
    responsavel_id: int | None = None


class EtapaIn(In):
    nome: Nome
    descricao: Texto = ""
    sequencia: int | None = Field(None, ge=1)
    entradas: list[Curto] = Field(default_factory=list, max_length=50)
    saidas: list[Curto] = Field(default_factory=list, max_length=50)
    opcional: bool = False
    condicao: Curto = ""


class EtapaUpdate(In):
    nome: Nome | None = None
    descricao: Texto | None = None
    sequencia: int | None = Field(None, ge=1)
    entradas: list[Curto] | None = Field(None, max_length=50)
    saidas: list[Curto] | None = Field(None, max_length=50)
    opcional: bool | None = None
    condicao: Curto | None = None


class OperacaoIn(In):
    nome: Nome
    descricao: Texto = ""
    sequencia: int | None = Field(None, ge=1)
    formula_tipo: Literal["linear", "lote", "fixo"] = "linear"
    unidade_medida: Annotated[str, Field(max_length=30)] = "un"
    recurso_padrao_id: int | None = None
    dados_medidos: list[Annotated[str, Field(max_length=40)]] = Field(
        default_factory=lambda: ["tempo", "quantidade"], max_length=30)
    campos_extras: list[CampoExtra] = Field(default_factory=list, max_length=30)
    ergonomia: Ergonomia = Field(default_factory=Ergonomia)


class OperacaoUpdate(In):
    nome: Nome | None = None
    descricao: Texto | None = None
    sequencia: int | None = Field(None, ge=1)
    formula_tipo: Literal["linear", "lote", "fixo"] | None = None
    unidade_medida: Annotated[str, Field(max_length=30)] | None = None
    recurso_padrao_id: int | None = None
    dados_medidos: list[Annotated[str, Field(max_length=40)]] | None = Field(None, max_length=30)
    campos_extras: list[CampoExtra] | None = Field(None, max_length=30)
    ergonomia: Ergonomia | None = None


class OperacaoOut(Out):
    id: int
    etapa_id: int
    sequencia: int
    nome: str
    descricao: str
    formula_tipo: str
    unidade_medida: str
    recurso_padrao_id: int | None
    dados_medidos: list
    campos_extras: list
    ergonomia: dict
    alerta_ergonomia: bool = False


class EtapaOut(Out):
    id: int
    processo_id: int
    sequencia: int
    nome: str
    descricao: str
    entradas: list
    saidas: list
    opcional: bool
    condicao: str
    operacoes: list[OperacaoOut] = []


class ProcessoOut(Out):
    id: int
    unidade_id: int
    codigo: str
    versao: int
    nome: str
    macroprocesso: str
    descricao: str
    status: str
    origem: str
    responsavel_id: int | None
    publicado_em: datetime | None
    etapas: list[EtapaOut] | None = None
    avisos: list[str] = []


# ------------------------------------------------------------------ parâmetros
class ParametroIn(In):
    escopo_tipo: Literal["operacao", "recurso", "processo"]
    escopo_id: int
    nome: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")]
    valor_num: float | None = None
    valor_texto: Curto | None = None
    unidade: Annotated[str, Field(max_length=30)] = ""
    origem: Literal["informado", "medido"] = "informado"
    justificativa: Texto = ""


class ParametroOut(Out):
    id: int
    escopo_tipo: str
    escopo_id: int
    nome: str
    valor_num: float | None
    valor_texto: str | None
    unidade: str
    origem: str
    status_validacao: str
    versao: int
    vigente: bool
    justificativa: str
    criado_em: datetime
    validado_em: datetime | None


class DecisaoIn(In):
    observacao: Annotated[str, Field(max_length=2000)] = ""


# ------------------------------------------------------------------ recursos e cadastros
class RecursoIn(In):
    unidade_id: int
    nome: Nome
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao"] = "maquina"
    processos_relacionados: list[Curto] = Field(default_factory=list, max_length=50)
    capacidade: float | None = Field(None, ge=0)
    capacidade_unidade: Annotated[str, Field(max_length=40)] = "un/h"
    equipes_habilitadas: list[Curto] = Field(default_factory=list, max_length=50)
    local_posto: Curto = ""
    horas_disponiveis_dia: float = Field(8.0, gt=0, le=24)
    ultima_manutencao: date | None = None
    proxima_manutencao: date | None = None


class RecursoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao"] | None = None
    processos_relacionados: list[Curto] | None = Field(None, max_length=50)
    capacidade: float | None = Field(None, ge=0)
    capacidade_unidade: Annotated[str, Field(max_length=40)] | None = None
    equipes_habilitadas: list[Curto] | None = Field(None, max_length=50)
    local_posto: Curto | None = None
    horas_disponiveis_dia: float | None = Field(None, gt=0, le=24)
    ultima_manutencao: date | None = None
    proxima_manutencao: date | None = None
    ativo: bool | None = None


class RecursoOut(Out):
    id: int
    unidade_id: int
    nome: str
    tipo: str
    processos_relacionados: list
    capacidade: float | None
    capacidade_unidade: str
    equipes_habilitadas: list
    local_posto: str
    horas_disponiveis_dia: float
    ultima_manutencao: date | None
    proxima_manutencao: date | None
    origem: str
    ativo: bool
    tempo_medio_min: float | None = None  # min/unidade, calculado pelo histórico aprovado
    tempo_preparacao_medio_min: float | None = None


class PessoaIn(In):
    unidade_id: int
    nome: Nome
    funcao: Annotated[str, Field(max_length=120)] = ""
    equipe: Annotated[str, Field(max_length=120)] = ""
    habilitacoes: list[Curto] = Field(default_factory=list, max_length=50)
    usuario_id: int | None = None


class PessoaUpdate(In):
    nome: Nome | None = None
    funcao: Annotated[str, Field(max_length=120)] | None = None
    equipe: Annotated[str, Field(max_length=120)] | None = None
    habilitacoes: list[Curto] | None = Field(None, max_length=50)
    usuario_id: int | None = None
    ativo: bool | None = None


class PessoaOut(Out):
    id: int
    unidade_id: int
    nome: str
    funcao: str
    equipe: str
    habilitacoes: list
    usuario_id: int | None
    ativo: bool


class MaterialIn(In):
    nome: Nome
    tipo: Annotated[str, Field(max_length=80)] = ""
    unidade_medida: Annotated[str, Field(max_length=30)] = "un"
    caracteristicas: dict[str, Any] = Field(default_factory=dict)


class MaterialUpdate(In):
    nome: Nome | None = None
    tipo: Annotated[str, Field(max_length=80)] | None = None
    unidade_medida: Annotated[str, Field(max_length=30)] | None = None
    caracteristicas: dict[str, Any] | None = None
    ativo: bool | None = None


class MaterialOut(Out):
    id: int
    nome: str
    tipo: str
    unidade_medida: str
    caracteristicas: dict
    origem: str
    ativo: bool


class ProdutoIn(In):
    nome: Nome
    tipo: Literal["produto", "servico"] = "produto"
    descricao: Texto = ""
    caracteristicas: dict[str, Any] = Field(default_factory=dict)


class ProdutoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["produto", "servico"] | None = None
    descricao: Texto | None = None
    caracteristicas: dict[str, Any] | None = None
    ativo: bool | None = None


class ProdutoOut(Out):
    id: int
    nome: str
    tipo: str
    descricao: str
    caracteristicas: dict
    ativo: bool


# ------------------------------------------------------------------ ordens
class RecursoOperacaoIn(In):
    operacao_id: int
    recurso_id: int


class OrdemIn(In):
    unidade_id: int
    processo_id: int
    produto_id: int | None = None
    descricao: Curto = ""
    cliente: Nome | None = None
    quantidade: float = Field(gt=0, le=1e9)
    prazo: date | None = None
    observacoes: Texto = ""
    recursos: list[RecursoOperacaoIn] = Field(default_factory=list, max_length=200)
    pular_operacoes: list[int] = Field(default_factory=list, max_length=200)


class OrdemUpdate(In):
    cliente: Nome | None = None
    descricao: Curto | None = None
    prazo: date | None = None
    observacoes: Texto | None = None


class CancelarIn(In):
    motivo: Annotated[str, Field(min_length=3, max_length=2000)]


class OrdemOperacaoOut(Out):
    id: int
    ordem_id: int
    operacao_id: int | None
    sequencia: int
    etapa_nome: str
    nome: str
    recurso_id: int | None
    qtd_planejada: float
    formula_tipo: str
    tempo_prep_est_min: float | None
    tempo_exec_est_min: float | None
    fonte_estimativa: str
    amostras: int
    opcional: bool
    status: str
    iniciada_em: datetime | None
    concluida_em: datetime | None
    qtd_boa: float = 0
    qtd_refugo: float = 0
    tempo_apontado_min: float = 0
    ordem_numero: str | None = None
    campos_extras: list = []
    dados_medidos: list = []


class OrdemOut(Out):
    id: int
    unidade_id: int
    numero: str
    cliente: str
    produto_id: int | None
    descricao: str
    quantidade: float
    prazo: date | None
    processo_id: int
    status: str
    tempo_estimado_min: float | None
    observacoes: str
    cancelamento_motivo: str
    criada_em: datetime
    liberada_em: datetime | None
    iniciada_em: datetime | None
    concluida_em: datetime | None
    atrasada: bool = False
    estimativa_parcial: bool = False
    operacoes: list[OrdemOperacaoOut] | None = None


# ------------------------------------------------------------------ apontamentos / ocorrências
TipoApont = Literal["preparacao", "execucao", "espera", "retrabalho"]


class IniciarApontamentoIn(In):
    ordem_operacao_id: int
    tipo: TipoApont = "execucao"
    pessoa_id: int | None = None
    recurso_id: int | None = None
    observacao: Texto = ""


class FinalizarApontamentoIn(In):
    quantidade_boa: float = Field(0, ge=0, le=1e9)
    quantidade_refugo: float = Field(0, ge=0, le=1e9)
    dados_extras: dict[str, Any] = Field(default_factory=dict)
    observacao: Texto | None = None
    fim: UTC | None = None


class ApontamentoManualIn(In):
    ordem_operacao_id: int
    tipo: TipoApont = "execucao"
    pessoa_id: int | None = None
    recurso_id: int | None = None
    inicio: UTC
    fim: UTC
    quantidade_boa: float = Field(0, ge=0, le=1e9)
    quantidade_refugo: float = Field(0, ge=0, le=1e9)
    dados_extras: dict[str, Any] = Field(default_factory=dict)
    observacao: Texto = ""


class AnularIn(In):
    motivo: Annotated[str, Field(min_length=5, max_length=2000)]


class ApontamentoOut(Out):
    id: int
    unidade_id: int
    ordem_id: int
    ordem_operacao_id: int
    tipo: str
    pessoa_id: int | None
    recurso_id: int | None
    inicio: datetime
    fim: datetime | None
    duracao_min: float | None = None
    ordem_numero: str | None = None
    operacao_nome: str | None = None
    quantidade_boa: float
    quantidade_refugo: float
    dados_extras: dict
    observacao: str
    status: str
    registrado_por: int
    anulado: bool
    anulado_motivo: str
    avisos: list[str] = []


class OcorrenciaIn(In):
    unidade_id: int | None = None
    ordem_id: int | None = None
    ordem_operacao_id: int | None = None
    recurso_id: int | None = None
    tipo: Literal["parada", "retrabalho", "falta_material", "ajuste", "qualidade", "outro"]
    causa: Annotated[str, Field(max_length=200)] = ""
    descricao: Texto = ""
    impacto: Curto = ""
    inicio: UTC | None = None
    fim: UTC | None = None


class FecharOcorrenciaIn(In):
    fim: UTC | None = None


class OcorrenciaOut(Out):
    id: int
    unidade_id: int
    ordem_id: int | None
    ordem_operacao_id: int | None
    recurso_id: int | None
    tipo: str
    causa: str
    descricao: str
    impacto: str
    inicio: datetime
    fim: datetime | None
    duracao_min: float | None = None
    anulada: bool


# ------------------------------------------------------------------ IA
class AnaliseIn(In):
    tipo: Literal["analise_desvio", "analise_gargalo", "relatorio_gestor",
                  "indicadores_sugeridos", "processos_semelhantes"]
    unidade_id: int
    ordem_id: int | None = None
    de: date | None = None
    ate: date | None = None


class RecomendacaoOut(Out):
    id: int
    unidade_id: int
    tipo: str
    titulo: str
    conteudo: dict
    evidencias: dict
    justificativa: str
    status: str
    provedor: str
    alvo_tipo: str | None
    alvo_id: int | None
    criada_em: datetime
    decidida_em: datetime | None
    decisao_obs: str
    aviso: str = "Sugestão gerada por IA. Não é um fato: requer validação do responsável."


class RecomendacaoEditIn(In):
    conteudo: dict[str, Any]


class AuditoriaOut(Out):
    id: int
    usuario_id: int | None
    acao: str
    entidade: str
    entidade_id: int | None
    antes: dict | None
    depois: dict | None
    ip: str
    em: datetime
