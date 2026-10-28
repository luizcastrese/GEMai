"""Esquemas de entrada/saída da API (validação rígida na borda)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from .services.modulos.catalogo import ChaveModulo

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


class Levantamento(In):
    """Entradas da equação revisada do NIOSH (unidades métricas)."""
    carga_kg: float | None = Field(None, ge=0, le=1000)
    h_cm: float | None = Field(None, ge=0, le=300)
    v_cm: float | None = Field(None, ge=0, le=300)
    d_cm: float | None = Field(None, ge=0, le=300)
    a_graus: float | None = Field(None, ge=0, le=180)
    freq_por_min: float | None = Field(None, ge=0, le=60)
    duracao: Literal["ate_1h", "1_2h", "2_8h"] | None = None
    pega: Literal["boa", "regular", "ruim"] | None = None


TipoMov = Literal["", "alcance_curto", "transporte_passos", "levantamento_curvado", "posicionamento_preciso",
                  "empurrar_puxar", "giro_tronco", "repetitivo_fino", "outro"]
Postura = Literal["", "em_pe", "sentado", "alternada", "agachado", "curvado"]

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


class LigacaoModuloIn(In):
    metodo: Literal["parafuso", "cavilha", "minifix", "dobradica", "corredica", "cola", "prego", "encaixe", "puxador", "outro"]
    fixadores: int = Field(0, ge=0, le=5000)


class ModuloParametros(In):
    """CONDIÇÕES do módulo de tempo de uma operação (nunca tempos): o sistema calcula a partir delas."""

    furos_por_peca: int | None = Field(None, ge=0, le=2000)
    bordas_m_por_peca: float | None = Field(None, ge=0, le=200)
    pecas_por_unidade: float | None = Field(None, ge=0, le=10000)
    ligacoes: list[LigacaoModuloIn] = Field(default_factory=list, max_length=50)


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
    funcao_requerida: Annotated[str, Field(max_length=120)] = ""
    num_pessoas: int = Field(1, ge=1, le=50)
    espaco_origem_id: int | None = None
    espaco_destino_id: int | None = None
    distancia_m: float | None = Field(None, ge=0, le=100000)
    item_peso_kg: float | None = Field(None, ge=0, le=100000)
    item_comprimento_m: float | None = Field(None, ge=0, le=1000)
    item_largura_m: float | None = Field(None, ge=0, le=1000)
    item_altura_m: float | None = Field(None, ge=0, le=1000)
    inicio_marco: Curto = ""
    fim_marco: Curto = ""
    perfil_id: int | None = None
    tipo_movimento: TipoMov = ""
    postura_trabalho: Postura = ""
    altura_trabalho_m: float | None = Field(None, ge=0, le=3)
    gasto_energetico_kcal_min: float | None = Field(None, ge=0, le=30)
    levantamento: Levantamento | None = None
    modulo: ChaveModulo | None = None
    modulo_parametros: ModuloParametros = Field(default_factory=ModuloParametros)


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
    funcao_requerida: Annotated[str, Field(max_length=120)] | None = None
    num_pessoas: int | None = Field(None, ge=1, le=50)
    espaco_origem_id: int | None = None
    espaco_destino_id: int | None = None
    distancia_m: float | None = Field(None, ge=0, le=100000)
    item_peso_kg: float | None = Field(None, ge=0, le=100000)
    item_comprimento_m: float | None = Field(None, ge=0, le=1000)
    item_largura_m: float | None = Field(None, ge=0, le=1000)
    item_altura_m: float | None = Field(None, ge=0, le=1000)
    inicio_marco: Curto | None = None
    fim_marco: Curto | None = None
    perfil_id: int | None = None
    tipo_movimento: TipoMov | None = None
    postura_trabalho: Postura | None = None
    altura_trabalho_m: float | None = Field(None, ge=0, le=3)
    gasto_energetico_kcal_min: float | None = Field(None, ge=0, le=30)
    levantamento: Levantamento | None = None
    modulo: ChaveModulo | None = None
    modulo_parametros: ModuloParametros | None = None


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
    funcao_requerida: str = ""
    num_pessoas: int = 1
    espaco_origem_id: int | None = None
    espaco_destino_id: int | None = None
    distancia_m: float | None = None
    item_peso_kg: float | None = None
    item_comprimento_m: float | None = None
    item_largura_m: float | None = None
    item_altura_m: float | None = None
    inicio_marco: str = ""
    fim_marco: str = ""
    perfil_id: int | None = None
    tipo_movimento: str = ""
    postura_trabalho: str = ""
    altura_trabalho_m: float | None = None
    gasto_energetico_kcal_min: float | None = None
    levantamento: dict | None = None
    modulo: str | None = None
    modulo_parametros: dict = {}


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
    fonte_url: str | None = None
    fonte_data: date | None = None
    confianca: str | None = None
    criado_em: datetime
    validado_em: datetime | None


class DecisaoIn(In):
    observacao: Annotated[str, Field(max_length=2000)] = ""


# ------------------------------------------------------------------ recursos e cadastros
FuncaoMeio = Literal["", "corte", "furacao", "bordo", "movimentacao", "acabamento", "montagem", "outro"]


class RecursoIn(In):
    unidade_id: int
    nome: Nome
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao", "meio_movimentacao"] = "maquina"
    processos_relacionados: list[Curto] = Field(default_factory=list, max_length=50)
    capacidade: float | None = Field(None, ge=0)
    capacidade_unidade: Annotated[str, Field(max_length=40)] = "un/h"
    equipes_habilitadas: list[Curto] = Field(default_factory=list, max_length=50)
    local_posto: Curto = ""
    horas_disponiveis_dia: float = Field(8.0, gt=0, le=24)
    espaco_id: int | None = None
    funcao: FuncaoMeio = ""
    marca: Annotated[str, Field(max_length=120)] = ""
    modelo: Annotated[str, Field(max_length=200)] = ""
    modelo_confirmado: bool = False
    ultima_manutencao: date | None = None
    proxima_manutencao: date | None = None


class RecursoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["maquina", "posto", "ferramenta", "instalacao", "meio_movimentacao"] | None = None
    processos_relacionados: list[Curto] | None = Field(None, max_length=50)
    capacidade: float | None = Field(None, ge=0)
    capacidade_unidade: Annotated[str, Field(max_length=40)] | None = None
    equipes_habilitadas: list[Curto] | None = Field(None, max_length=50)
    local_posto: Curto | None = None
    horas_disponiveis_dia: float | None = Field(None, gt=0, le=24)
    espaco_id: int | None = None
    funcao: FuncaoMeio | None = None
    marca: Annotated[str, Field(max_length=120)] | None = None
    modelo: Annotated[str, Field(max_length=200)] | None = None
    modelo_confirmado: bool | None = None
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
    espaco_id: int | None = None
    funcao: str = ""
    marca: str = ""
    modelo: str = ""
    modelo_confirmado: bool = False
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
    perfil_id: int | None = None
    ritmo_pct: float | None = Field(None, ge=50, le=150)  # ao informar, a origem passa a "informado"


class PessoaUpdate(In):
    nome: Nome | None = None
    funcao: Annotated[str, Field(max_length=120)] | None = None
    equipe: Annotated[str, Field(max_length=120)] | None = None
    habilitacoes: list[Curto] | None = Field(None, max_length=50)
    usuario_id: int | None = None
    perfil_id: int | None = None
    ritmo_pct: float | None = Field(None, ge=50, le=150)  # None explícito limpa o ritmo da pessoa
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
    perfil_id: int | None = None
    ritmo_pct: float | None = None
    ritmo_origem: str = ""  # "" | informado | calibrado
    ritmo_amostras: int = 0
    ritmo_calibrado_em: datetime | None = None
    # Ritmo usado na normalização do histórico (pessoa > perfil > 100); só preenchido nas listagens/consultas.
    ritmo_efetivo: float | None = None
    ritmo_efetivo_origem: str = ""  # pessoa | perfil | padrao


class CalibrarRitmoIn(In):
    unidade_id: int | None = None
    aplicar: bool = False  # False = prévia, nada é gravado


class RitmoPessoaOut(BaseModel):
    pessoa_id: int
    nome: str
    unidade_id: int
    status: Literal["sugerido", "mantido", "insuficiente"]
    aplicado: bool
    ritmo_atual: float
    ritmo_atual_origem: str  # informado | calibrado | perfil | padrao
    ritmo_sugerido: float | None
    operacoes_usadas: int
    amostras: int
    motivo: str = ""


class CalibrarRitmoOut(BaseModel):
    aplicado: bool
    aviso: str
    criterios: dict
    operacoes_consideradas: int
    operacoes_ignoradas: list[str]
    aplicadas: int
    pessoas: list[RitmoPessoaOut]


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


# ------------------------------------------------------------------ gêmeo digital
class EspacoIn(In):
    unidade_id: int
    nome: Nome
    tipo: Literal["area", "posto", "estoque", "expedicao", "montagem"] = "area"
    comprimento_m: float | None = Field(None, gt=0, le=10000)
    largura_m: float | None = Field(None, gt=0, le=10000)
    pe_direito_m: float | None = Field(None, gt=0, le=100)
    piso: Annotated[str, Field(max_length=80)] = ""
    temperatura_c: float | None = Field(None, ge=-60, le=80)
    umidade_pct: float | None = Field(None, ge=0, le=100)
    ruido_db: float | None = Field(None, ge=0, le=200)
    iluminancia_lux: float | None = Field(None, ge=0, le=200000)
    tolerancia_ambiente_pct: float | None = Field(None, ge=0, le=30, deprecated=True, description="OBSOLETO: não entra mais no cálculo.")
    observacoes: Texto = ""


class EspacoUpdate(In):
    nome: Nome | None = None
    tipo: Literal["area", "posto", "estoque", "expedicao", "montagem"] | None = None
    comprimento_m: float | None = Field(None, gt=0, le=10000)
    largura_m: float | None = Field(None, gt=0, le=10000)
    pe_direito_m: float | None = Field(None, gt=0, le=100)
    piso: Annotated[str, Field(max_length=80)] | None = None
    temperatura_c: float | None = Field(None, ge=-60, le=80)
    umidade_pct: float | None = Field(None, ge=0, le=100)
    ruido_db: float | None = Field(None, ge=0, le=200)
    iluminancia_lux: float | None = Field(None, ge=0, le=200000)
    tolerancia_ambiente_pct: float | None = Field(None, ge=0, le=30, deprecated=True, description="OBSOLETO: não entra mais no cálculo.")
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


class ModeloTempoOut(Out):
    id: int
    operacao_id: int
    versao: int
    elementos: list
    fator_ambiente: float
    ritmo_pct: float = 100.0
    tolerancias: list = []
    premissas: list
    dados_faltantes: list
    padrao_apontamento: dict
    confianca: str
    justificativa: str
    origem: str
    provedor: str
    status_validacao: str
    criado_em: datetime
    validado_em: datetime | None
    aviso: str = "Estimativa gerada por IA: não é um fato. Compare com medições e valide."


class ModeloTempoManualIn(In):
    elementos: list[dict[str, Any]] = Field(max_length=15)
    fator_ambiente: float = Field(1.0, ge=0.5, le=3.0)
    ritmo_pct: float = Field(100.0, ge=50, le=150)
    tolerancias: list[dict[str, Any]] = Field(default_factory=list, max_length=15)
    premissas: list[Curto] = Field(default_factory=list, max_length=20)
    justificativa: Texto = ""


class EstimativaOut(BaseModel):
    fonte: str
    validada: bool
    quantidade: float
    preparacao_min: float | None
    execucao_min: float | None
    total_min: float | None
    elementos: list | None = None
    avisos: list[str] = []


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
    detalhe_estimativa: list | None = None
    estimativa_validada: bool = True
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
    processo_id: int | None = None
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
                  "indicadores_sugeridos", "processos_semelhantes", "revisao_processo"]
    unidade_id: int
    ordem_id: int | None = None
    processo_id: int | None = None
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
    fadiga_pct_hora: float = Field(0.0, ge=0, le=10, deprecated=True, description="OBSOLETO: ignorado (a fadiga por turno só entra quando aprendida dos dados).")


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
    modulo: str = ""
    modulo_versao: int = 0
    parametros_modulo: dict = {}
    coeficientes: list = []
    tempo_normal_min: float | None = None
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
    hierarquia: dict | None = None  # produto → grupo → módulo → elementos (normal, tolerâncias, padrão, preparação)


class PlanoOrdemIn(In):
    cliente: Nome | None = None
    prazo: date | None = None


# ------------------------------------------------------------------ meios (cadastro assistido)
class IdentificarMeioIn(In):
    unidade_id: int
    texto: Annotated[str, Field(min_length=2, max_length=500)]
    foto_base64: str | None = Field(None, max_length=8_000_000)  # opcional; só JPEG/PNG; descartada após o uso


class IdentificarMeioOut(BaseModel):
    candidatos: list[dict]
    pergunta: str | None = None
    provedor: str
    aviso: str = ""
    confirmacao_necessaria: bool = True


class BuscarFichaIn(In):
    pass


class BuscarFichaOut(BaseModel):
    encontrada: bool
    sugeridos: list[ParametroOut]
    descartados: list[dict]
    pendencias: list[str]
    provedor: str
    aviso: str = ""
    aviso_fonte: str = "Valores achados na web são sugestões pendentes: confira a fonte e valide para entrarem no cálculo."


class FichaMeioOut(BaseModel):
    recurso_id: int
    nome: str
    marca: str
    modelo: str
    modelo_confirmado: bool
    funcao: str
    parametros: list[dict]
    pendencias: list[str]
    busca_disponivel: bool


class SugestaoModuloOut(BaseModel):
    modulo: str | None
    titulo: str | None = None
    justificativa: str = ""
    faltantes: list[str] = []  # o que ainda falta para o módulo sugerido calcular o tempo (condições, não tempos)
    provedor: str
    aviso: str = ""
    aplicar_com: str = "PATCH /operacoes/{id} com {\"modulo\": ...}: a sugestão só vale depois que uma pessoa a aplica."
