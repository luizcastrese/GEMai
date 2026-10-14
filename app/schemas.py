"""Esquemas de entrada/saída da API (validação rígida na borda)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator


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
    ativo: bool
    unidade_ids: list[int] = []  # vazio = todas as unidades


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioOut


class UsuarioIn(In):
    nome: Nome
    email: EmailStr
    senha: Annotated[str, Field(max_length=128)]
    unidade_ids: list[int] = []  # vazio = todas as unidades


class UsuarioUpdate(In):
    nome: Nome | None = None
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


_HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class JornadaTrabalho(BaseModel):
    """Horário de trabalho da equipe: blocos [início, fim] sem sobreposição."""
    model_config = ConfigDict(extra="forbid")
    blocos: list[Annotated[list[_HHMM], Field(min_length=2, max_length=2)]] = Field(min_length=1, max_length=6)
    so_dias_uteis: bool = True

    @model_validator(mode="after")
    def _blocos_validos(self):
        ordenados = sorted(self.blocos)
        if any(fim <= ini for ini, fim in ordenados):
            raise ValueError("Cada bloco da jornada deve terminar depois de começar.")
        if any(f1 > i2 for (_, f1), (i2, _) in zip(ordenados, ordenados[1:])):
            raise ValueError("Os blocos da jornada não podem se sobrepor.")
        return self


class UnidadeUpdate(In):
    nome: Nome | None = None
    equipe_pessoas: int | None = Field(None, ge=1, le=50)
    perfil_equipe_id: int | None = None
    jornada: JornadaTrabalho | None = None
    ativa: bool | None = None


class UnidadeOut(Out):
    id: int
    nome: str
    equipe_pessoas: int | None = None
    perfil_equipe_id: int | None = None
    jornada: dict | None = None
    ativa: bool


Nivel = Literal["baixo", "medio", "alto"]


TipoMov = Literal["", "alcance_curto", "transporte_passos", "levantamento_curvado", "posicionamento_preciso",
                  "empurrar_puxar", "giro_tronco", "repetitivo_fino", "outro"]
Postura = Literal["", "em_pe", "sentado", "alternada", "agachado", "curvado"]

class DecisaoIn(In):
    observacao: Annotated[str, Field(max_length=2000)] = ""


# ------------------------------------------------------------------ recursos e cadastros
class RecursoIn(In):
    unidade_id: int
    nome: Nome
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao"] = "maquina"
    capacidade: float | None = Field(None, ge=0)
    capacidade_unidade: Annotated[str, Field(max_length=40)] = "un/h"
    equipes_habilitadas: list[Curto] = Field(default_factory=list, max_length=50)
    local_posto: Curto = ""
    horas_disponiveis_dia: float = Field(8.0, gt=0, le=24)
    espaco_id: int | None = None
    funcao: Literal["", "corte", "furacao", "bordo", "acabamento", "montagem", "outro"] = ""
    ultima_manutencao: date | None = None
    proxima_manutencao: date | None = None


class RecursoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao"] | None = None
    capacidade: float | None = Field(None, ge=0)
    capacidade_unidade: Annotated[str, Field(max_length=40)] | None = None
    equipes_habilitadas: list[Curto] | None = Field(None, max_length=50)
    local_posto: Curto | None = None
    horas_disponiveis_dia: float | None = Field(None, gt=0, le=24)
    espaco_id: int | None = None
    funcao: Literal["", "corte", "furacao", "bordo", "acabamento", "montagem", "outro"] | None = None
    ultima_manutencao: date | None = None
    proxima_manutencao: date | None = None
    ativo: bool | None = None


class RecursoOut(Out):
    id: int
    unidade_id: int
    nome: str
    tipo: str
    capacidade: float | None
    capacidade_unidade: str
    equipes_habilitadas: list
    local_posto: str
    horas_disponiveis_dia: float
    espaco_id: int | None = None
    funcao: str = ""
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
    peso_kg: float | None = Field(None, ge=0, le=100000)
    comprimento_m: float | None = Field(None, ge=0, le=1000)
    largura_m: float | None = Field(None, ge=0, le=1000)
    altura_m: float | None = Field(None, ge=0, le=1000)


class ProdutoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["produto", "servico"] | None = None
    descricao: Texto | None = None
    caracteristicas: dict[str, Any] | None = None
    peso_kg: float | None = Field(None, ge=0, le=100000)
    comprimento_m: float | None = Field(None, ge=0, le=1000)
    largura_m: float | None = Field(None, ge=0, le=1000)
    altura_m: float | None = Field(None, ge=0, le=1000)
    ativo: bool | None = None


class ProdutoOut(Out):
    id: int
    nome: str
    tipo: str
    descricao: str
    caracteristicas: dict
    peso_kg: float | None = None
    comprimento_m: float | None = None
    largura_m: float | None = None
    altura_m: float | None = None
    ativo: bool


# ------------------------------------------------------------------ agentes e ambiente
class EspacoIn(In):
    unidade_id: int
    nome: Nome
    tipo: Literal["area", "posto", "estoque", "expedicao", "montagem"] = "area"
    comprimento_m: float | None = Field(None, gt=0, le=10000)
    largura_m: float | None = Field(None, gt=0, le=10000)
    pe_direito_m: float | None = Field(None, gt=0, le=100)
    altura_trabalho_m: float | None = Field(None, ge=0.3, le=2.5)
    piso: Annotated[str, Field(max_length=80)] = ""
    temperatura_c: float | None = Field(None, ge=-60, le=80)
    umidade_pct: float | None = Field(None, ge=0, le=100)
    ruido_db: float | None = Field(None, ge=0, le=200)
    iluminancia_lux: float | None = Field(None, ge=0, le=200000)
    tolerancia_ambiente_pct: float | None = Field(None, ge=0, le=30)
    observacoes: Texto = ""


class EspacoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["area", "posto", "estoque", "expedicao", "montagem"] | None = None
    comprimento_m: float | None = Field(None, gt=0, le=10000)
    largura_m: float | None = Field(None, gt=0, le=10000)
    pe_direito_m: float | None = Field(None, gt=0, le=100)
    altura_trabalho_m: float | None = Field(None, ge=0.3, le=2.5)
    piso: Annotated[str, Field(max_length=80)] | None = None
    temperatura_c: float | None = Field(None, ge=-60, le=80)
    umidade_pct: float | None = Field(None, ge=0, le=100)
    ruido_db: float | None = Field(None, ge=0, le=200)
    iluminancia_lux: float | None = Field(None, ge=0, le=200000)
    tolerancia_ambiente_pct: float | None = Field(None, ge=0, le=30)
    observacoes: Texto | None = None
    ativo: bool | None = None


class EspacoOut(Out):
    id: int
    unidade_id: int
    nome: str
    tipo: str
    comprimento_m: float | None
    largura_m: float | None
    pe_direito_m: float | None
    altura_trabalho_m: float | None = None
    piso: str
    temperatura_c: float | None
    umidade_pct: float | None = None
    ruido_db: float | None = None
    iluminancia_lux: float | None = None
    tolerancia_ambiente_pct: float | None = None
    observacoes: str
    origem: str
    ativo: bool


class PerfilIn(In):
    unidade_id: int
    nome: Nome
    sexo: Literal["feminino", "masculino", "misto", "nao_informado"] = "nao_informado"
    estatura_cm: float | None = Field(None, ge=50, le=250)
    peso_corporal_kg: float | None = Field(None, ge=10, le=400)
    altura_cotovelo_cm: float | None = Field(None, ge=30, le=200)
    faixa_etaria: Literal["adulto", "menor_18"] = "adulto"
    experiencia: Literal["iniciante", "intermediario", "experiente"] = "intermediario"
    ritmo_pct: float = Field(100.0, ge=50, le=150)
    limite_energetico_kcal_min: float | None = Field(None, gt=1.5, le=30)
    observacoes: Texto = ""


class PerfilUpdate(In):
    nome: Nome | None = None
    sexo: Literal["feminino", "masculino", "misto", "nao_informado"] | None = None
    estatura_cm: float | None = Field(None, ge=50, le=250)
    peso_corporal_kg: float | None = Field(None, ge=10, le=400)
    altura_cotovelo_cm: float | None = Field(None, ge=30, le=200)
    faixa_etaria: Literal["adulto", "menor_18"] | None = None
    experiencia: Literal["iniciante", "intermediario", "experiente"] | None = None
    ritmo_pct: float | None = Field(None, ge=50, le=150)
    limite_energetico_kcal_min: float | None = Field(None, gt=1.5, le=30)
    observacoes: Texto | None = None
    ativo: bool | None = None


class PerfilOut(Out):
    id: int
    unidade_id: int
    nome: str
    sexo: str
    estatura_cm: float | None
    peso_corporal_kg: float | None
    altura_cotovelo_cm: float | None
    faixa_etaria: str
    experiencia: str
    ritmo_pct: float
    limite_energetico_kcal_min: float | None
    observacoes: str
    ativo: bool


class DistanciaIn(In):
    origem_id: int
    destino_id: int
    metros: float = Field(ge=0, le=100000)


class DistanciaOut(Out):
    id: int
    unidade_id: int
    origem_id: int
    destino_id: int
    metros: float


# ------------------------------------------------------------------ ordens
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
    sequencia: int
    etapa_nome: str
    nome: str
    recurso_id: int | None
    qtd_planejada: float
    tempo_prep_est_min: float | None
    tempo_exec_est_min: float | None
    fonte_estimativa: str
    detalhe_estimativa: list | None = None
    status: str
    iniciada_em: datetime | None
    concluida_em: datetime | None
    qtd_boa: float = 0
    qtd_refugo: float = 0
    tempo_apontado_min: float = 0
    ordem_numero: str | None = None


class OrdemOut(Out):
    id: int
    unidade_id: int
    numero: str
    cliente: str
    produto_id: int | None
    descricao: str
    quantidade: float
    prazo: date | None
    plano_id: int | None = None
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
    tipo: Literal["analise_desvio", "analise_gargalo", "relatorio_gestor"]
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


# ------------------------------------------------------------------ produto → plano de trabalho
METODOS = Literal["parafuso", "cavilha", "minifix", "dobradica", "corredica", "cola", "prego", "encaixe", "puxador", "outro"]


class ComponenteIn(In):
    nome: Nome
    quantidade: float = Field(1.0, gt=0, le=100000)
    material: Annotated[str, Field(max_length=80)] = ""
    grupo: Annotated[str, Field(max_length=80)] = "Corpo"
    comprimento_m: float | None = Field(None, gt=0, le=100)
    largura_m: float | None = Field(None, gt=0, le=100)
    espessura_m: float | None = Field(None, gt=0, le=10)
    peso_kg: float | None = Field(None, ge=0, le=100000)
    furos: int = Field(0, ge=0, le=10000)
    bordas_m: float | None = Field(None, ge=0, le=1000)


class ComponenteUpdate(In):
    nome: Nome | None = None
    quantidade: float | None = Field(None, gt=0, le=100000)
    material: Annotated[str, Field(max_length=80)] | None = None
    grupo: Annotated[str, Field(max_length=80)] | None = None
    comprimento_m: float | None = Field(None, gt=0, le=100)
    largura_m: float | None = Field(None, gt=0, le=100)
    espessura_m: float | None = Field(None, gt=0, le=10)
    peso_kg: float | None = Field(None, ge=0, le=100000)
    furos: int | None = Field(None, ge=0, le=10000)
    bordas_m: float | None = Field(None, ge=0, le=1000)


class ComponenteOut(Out):
    id: int
    produto_id: int
    nome: str
    quantidade: float
    material: str
    grupo: str
    comprimento_m: float | None
    largura_m: float | None
    espessura_m: float | None
    peso_kg: float | None
    peso_estimado_kg: float | None = None  # calculado por material e medidas; só exibição
    furos: int
    bordas_m: float | None


class LigacaoIn(In):
    componente_id: int
    ligado_a_id: int | None = None
    metodo: METODOS = "parafuso"
    fixadores: int = Field(0, ge=0, le=10000)


class LigacaoOut(Out):
    id: int
    produto_id: int
    componente_id: int
    ligado_a_id: int | None
    metodo: str
    fixadores: int


class EstruturaOut(Out):
    produto_id: int
    componentes: list[ComponenteOut]
    ligacoes: list[LigacaoOut]


class InterpretarProdutoIn(In):
    descricao: Annotated[str, Field(min_length=3, max_length=4000)]
    substituir: bool = False


class InterpretarProdutoOut(Out):
    componentes: list[ComponenteIn]
    ligacoes: list[dict]
    dados_faltantes: list[str]
    observacoes: str
    provedor: str
    aviso: str = ""


class AplicarEstruturaIn(In):
    componentes: list[ComponenteIn] = Field(max_length=300)
    ligacoes: list[dict] = Field(default_factory=list, max_length=600)
    substituir: bool = False


class ReferenciaIn(In):
    chave: Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z_]+(:[a-z_]+)?$")]
    minutos: float = Field(gt=0, le=600)


class ReferenciaOut(Out):
    chave: str
    minutos: float
    padrao_minutos: float | None = None
    informada: bool = False


class PlanoGerarIn(In):
    produto_id: int
    unidade_id: int
    quantidade: float = Field(1.0, gt=0, le=100000)
    nome: Annotated[str, Field(max_length=300)] | None = None
    inicio: UTC | None = None
    blocos: list[Annotated[list[Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]], Field(min_length=2, max_length=2)]] | None = Field(None, max_length=6)
    so_dias_uteis: bool = True
    pessoas: int = Field(1, ge=1, le=50)
    perfil_id: int | None = None
    fadiga_pct_hora: float = Field(0.0, ge=0, le=10)


class PlanoPassoOut(Out):
    id: int
    sequencia: int
    nome: str
    tipo: str
    grupo: str
    componentes: list
    qtd_pecas: float
    recurso_id: int | None
    espaco_origem_id: int | None
    espaco_destino_id: int | None
    pessoas: int
    elementos: list
    tolerancias: list
    ritmo_pct: float
    composicao: list
    tempo_prep_min: float | None
    tempo_exec_min: float | None
    tempo_padrao_min: float | None
    tempo_agendado_min: float | None
    faltantes: list
    alertas: list
    observacao: str
    inicio_prev: datetime | None
    fim_prev: datetime | None
    recurso_nome: str | None = None
    origem_nome: str | None = None
    destino_nome: str | None = None


class PlanoOut(Out):
    id: int
    unidade_id: int
    produto_id: int
    produto_nome: str | None = None
    nome: str
    quantidade: float
    status: str
    config: dict
    provedor: str
    confianca: str
    premissas: list
    faltantes: list
    alertas: list
    totais: dict
    ordem_id: int | None
    criado_em: datetime
    confirmado_em: datetime | None
    passos: list[PlanoPassoOut] | None = None


class PlanoOrdemIn(In):
    cliente: Nome | None = None
    prazo: date | None = None
