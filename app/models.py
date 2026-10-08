"""Modelo de dados (seção 14 do documento conceitual).

Toda tabela de negócio carrega `empresa_id` (isolamento multiempresa). Tabelas
operacionais carregam também `unidade_id` quando o acesso é restrito por unidade.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Grava sempre UTC; devolve sempre datetime com fuso."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime sem fuso horário")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def _pk() -> Mapped[int]:
    return mapped_column(Integer, primary_key=True)


def _empresa() -> Mapped[int]:
    return mapped_column(ForeignKey("empresas.id"), index=True)


# ---------------------------------------------------------------- cadastro
class Empresa(Base):
    __tablename__ = "empresas"
    id: Mapped[int] = _pk()
    nome: Mapped[str] = mapped_column(String(200))
    segmento: Mapped[str] = mapped_column(String(120), default="")
    documento: Mapped[str | None] = mapped_column(String(32))
    fuso: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    # Envio de dados da empresa a um provedor externo de IA exige consentimento explícito.
    permite_ia_externa: Mapped[bool] = mapped_column(Boolean, default=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    seq_ordem: Mapped[int] = mapped_column(Integer, default=0)
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)


class Unidade(Base):
    __tablename__ = "unidades"
    __table_args__ = (UniqueConstraint("empresa_id", "nome"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    nome: Mapped[str] = mapped_column(String(200))
    # Tela 1 – descrição da operação
    descricao_operacao: Mapped[str] = mapped_column(Text, default="")
    objetivo: Mapped[str] = mapped_column(Text, default="")
    principais_problemas: Mapped[str] = mapped_column(Text, default="")
    informacoes_disponiveis: Mapped[str] = mapped_column(Text, default="")
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(20))  # admin | gestor | operador
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    falhas_login: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(UTCDateTime)
    token_versao: Mapped[int] = mapped_column(Integer, default=0)  # invalida tokens emitidos
    ultimo_login: Mapped[datetime | None] = mapped_column(UTCDateTime)
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)

    unidades: Mapped[list["UsuarioUnidade"]] = relationship(cascade="all, delete-orphan")


class UsuarioUnidade(Base):
    __tablename__ = "usuario_unidades"
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), primary_key=True)


# ---------------------------------------------------------------- diagnóstico
class DiagnosticoPergunta(Base):
    __tablename__ = "diagnostico_perguntas"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    grupo: Mapped[str] = mapped_column(String(60))
    texto: Mapped[str] = mapped_column(Text)
    resposta: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    origem: Mapped[str] = mapped_column(String(60), default="heuristica")  # provedor que gerou
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    respondida_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    respondida_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))


# ---------------------------------------------------------------- processos
class Processo(Base):
    """Cada versão é uma linha imutável (após publicada); `codigo` agrupa as versões."""

    __tablename__ = "processos"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", "versao"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(36))
    versao: Mapped[int] = mapped_column(Integer, default=1)
    nome: Mapped[str] = mapped_column(String(200))
    macroprocesso: Mapped[str] = mapped_column(String(200), default="")
    descricao: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="rascunho")
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual | ia
    recomendacao_id: Mapped[int | None] = mapped_column(ForeignKey("recomendacoes_ia.id"))
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    publicado_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    publicado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    etapas: Mapped[list["Etapa"]] = relationship(
        back_populates="processo", order_by="Etapa.sequencia", cascade="all, delete-orphan"
    )


class Etapa(Base):
    __tablename__ = "etapas"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    processo_id: Mapped[int] = mapped_column(ForeignKey("processos.id"), index=True)
    sequencia: Mapped[int] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    entradas: Mapped[list] = mapped_column(JSON, default=list)
    saidas: Mapped[list] = mapped_column(JSON, default=list)
    opcional: Mapped[bool] = mapped_column(Boolean, default=False)  # caminho alternativo
    condicao: Mapped[str] = mapped_column(String(300), default="")

    processo: Mapped[Processo] = relationship(back_populates="etapas")
    operacoes: Mapped[list["Operacao"]] = relationship(
        back_populates="etapa", order_by="Operacao.sequencia", cascade="all, delete-orphan"
    )


class Operacao(Base):
    __tablename__ = "operacoes"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    etapa_id: Mapped[int] = mapped_column(ForeignKey("etapas.id"), index=True)
    sequencia: Mapped[int] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    formula_tipo: Mapped[str] = mapped_column(String(20), default="linear")
    unidade_medida: Mapped[str] = mapped_column(String(30), default="un")
    recurso_padrao_id: Mapped[int | None] = mapped_column(ForeignKey("recursos.id"))
    dados_medidos: Mapped[list] = mapped_column(JSON, default=lambda: ["tempo", "quantidade"])
    campos_extras: Mapped[list] = mapped_column(JSON, default=list)
    ergonomia: Mapped[dict] = mapped_column(JSON, default=dict)
    # Blocos do "lego": mão de obra, espaços e item físico típico
    funcao_requerida: Mapped[str] = mapped_column(String(120), default="")
    num_pessoas: Mapped[int] = mapped_column(Integer, default=1)
    espaco_origem_id: Mapped[int | None] = mapped_column(ForeignKey("espacos.id"))
    espaco_destino_id: Mapped[int | None] = mapped_column(ForeignKey("espacos.id"))
    distancia_m: Mapped[float | None] = mapped_column(Float)  # sobrepõe a tabela de distâncias
    item_peso_kg: Mapped[float | None] = mapped_column(Float)
    item_comprimento_m: Mapped[float | None] = mapped_column(Float)
    item_largura_m: Mapped[float | None] = mapped_column(Float)
    item_altura_m: Mapped[float | None] = mapped_column(Float)
    # Padrão de apontamento: quando começa/termina, para que o parâmetro seja medido de forma consistente
    inicio_marco: Mapped[str] = mapped_column(String(300), default="")
    fim_marco: Mapped[str] = mapped_column(String(300), default="")

    etapa: Mapped[Etapa] = relationship(back_populates="operacoes")


# ---------------------------------------------------------------- recursos
class Recurso(Base):
    __tablename__ = "recursos"
    __table_args__ = (UniqueConstraint("unidade_id", "nome"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(20), default="maquina")
    processos_relacionados: Mapped[list] = mapped_column(JSON, default=list)
    capacidade: Mapped[float | None] = mapped_column(Float)
    capacidade_unidade: Mapped[str] = mapped_column(String(40), default="un/h")
    equipes_habilitadas: Mapped[list] = mapped_column(JSON, default=list)
    local_posto: Mapped[str] = mapped_column(String(200), default="")
    horas_disponiveis_dia: Mapped[float] = mapped_column(Float, default=8.0)
    espaco_id: Mapped[int | None] = mapped_column(ForeignKey("espacos.id"))
    ultima_manutencao: Mapped[date | None] = mapped_column(Date)
    proxima_manutencao: Mapped[date | None] = mapped_column(Date)
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Pessoa(Base):
    __tablename__ = "pessoas"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    funcao: Mapped[str] = mapped_column(String(120), default="")
    equipe: Mapped[str] = mapped_column(String(120), default="")
    habilitacoes: Mapped[list] = mapped_column(JSON, default=list)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Material(Base):
    __tablename__ = "materiais"
    __table_args__ = (UniqueConstraint("empresa_id", "nome"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(80), default="")
    unidade_medida: Mapped[str] = mapped_column(String(30), default="un")
    caracteristicas: Mapped[dict] = mapped_column(JSON, default=dict)
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Produto(Base):
    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("empresa_id", "nome"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(20), default="produto")  # produto | servico
    descricao: Mapped[str] = mapped_column(Text, default="")
    caracteristicas: Mapped[dict] = mapped_column(JSON, default=dict)
    # Contorno físico do item (sobrepõe o item típico da operação no cálculo do modelo de tempo)
    peso_kg: Mapped[float | None] = mapped_column(Float)
    comprimento_m: Mapped[float | None] = mapped_column(Float)
    largura_m: Mapped[float | None] = mapped_column(Float)
    altura_m: Mapped[float | None] = mapped_column(Float)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- gêmeo digital
class Espaco(Base):
    """Contorno físico: área/posto/estoque onde as atividades acontecem."""

    __tablename__ = "espacos"
    __table_args__ = (UniqueConstraint("unidade_id", "nome"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(30), default="area")  # area | posto | estoque | expedicao
    comprimento_m: Mapped[float | None] = mapped_column(Float)
    largura_m: Mapped[float | None] = mapped_column(Float)
    pe_direito_m: Mapped[float | None] = mapped_column(Float)
    piso: Mapped[str] = mapped_column(String(80), default="")
    temperatura_c: Mapped[float | None] = mapped_column(Float)
    observacoes: Mapped[str] = mapped_column(Text, default="")
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Distancia(Base):
    """Distância (m) entre dois espaços. Vale nos dois sentidos."""

    __tablename__ = "distancias"
    __table_args__ = (UniqueConstraint("origem_id", "destino_id"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    origem_id: Mapped[int] = mapped_column(ForeignKey("espacos.id"))
    destino_id: Mapped[int] = mapped_column(ForeignKey("espacos.id"))
    metros: Mapped[float] = mapped_column(Float)


class ModeloTempo(Base):
    """Modelo de tempo de uma operação: elementos com fórmulas de vocabulário FECHADO.

    A IA propõe os elementos e coeficientes; o sistema calcula (sem executar código da IA).
    Cada nova geração cria uma versão; a ativa é a mais recente não rejeitada.
    """

    __tablename__ = "modelos_tempo"
    __table_args__ = (Index("ix_modelo_op", "empresa_id", "operacao_id"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    operacao_id: Mapped[int] = mapped_column(ForeignKey("operacoes.id"))
    versao: Mapped[int] = mapped_column(Integer, default=1)
    elementos: Mapped[list] = mapped_column(JSON, default=list)
    fator_ambiente: Mapped[float] = mapped_column(Float, default=1.0)
    premissas: Mapped[list] = mapped_column(JSON, default=list)
    dados_faltantes: Mapped[list] = mapped_column(JSON, default=list)
    padrao_apontamento: Mapped[dict] = mapped_column(JSON, default=dict)
    confianca: Mapped[str] = mapped_column(String(10), default="baixa")  # baixa | media | alta
    justificativa: Mapped[str] = mapped_column(Text, default="")
    origem: Mapped[str] = mapped_column(String(20), default="ia")  # ia | manual
    provedor: Mapped[str] = mapped_column(String(80), default="")
    status_validacao: Mapped[str] = mapped_column(String(20), default="pendente")
    contexto: Mapped[dict] = mapped_column(JSON, default=dict)  # retrato do contorno físico usado pela IA
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    validado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    validado_em: Mapped[datetime | None] = mapped_column(UTCDateTime)


# ---------------------------------------------------------------- parâmetros
class Parametro(Base):
    """Variável com origem e versão. Só `vigente` + validado entra nos cálculos."""

    __tablename__ = "parametros"
    __table_args__ = (Index("ix_param_escopo", "empresa_id", "escopo_tipo", "escopo_id", "nome"),)
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    escopo_tipo: Mapped[str] = mapped_column(String(20))  # operacao | recurso | processo
    escopo_id: Mapped[int] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(String(80))
    valor_num: Mapped[float | None] = mapped_column(Float)
    valor_texto: Mapped[str | None] = mapped_column(String(300))
    unidade: Mapped[str] = mapped_column(String(30), default="")
    origem: Mapped[str] = mapped_column(String(20), default="informado")
    status_validacao: Mapped[str] = mapped_column(String(20), default="pendente")
    versao: Mapped[int] = mapped_column(Integer, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=False)
    justificativa: Mapped[str] = mapped_column(Text, default="")
    recomendacao_id: Mapped[int | None] = mapped_column(ForeignKey("recomendacoes_ia.id"))
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    validado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    validado_em: Mapped[datetime | None] = mapped_column(UTCDateTime)


# ---------------------------------------------------------------- produção
class Ordem(Base):
    __tablename__ = "ordens"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero"),
        Index("ix_ordem_status", "empresa_id", "unidade_id", "status"),
    )
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    numero: Mapped[str] = mapped_column(String(20))
    cliente: Mapped[str] = mapped_column(String(200), default="")
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produtos.id"))
    descricao: Mapped[str] = mapped_column(String(300), default="")
    quantidade: Mapped[float] = mapped_column(Float)
    prazo: Mapped[date | None] = mapped_column(Date)
    processo_id: Mapped[int] = mapped_column(ForeignKey("processos.id"))
    status: Mapped[str] = mapped_column(String(20), default="planejada")
    tempo_estimado_min: Mapped[float | None] = mapped_column(Float)  # None = sem base
    observacoes: Mapped[str] = mapped_column(Text, default="")
    cancelamento_motivo: Mapped[str] = mapped_column(Text, default="")
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    liberada_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    iniciada_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    concluida_em: Mapped[datetime | None] = mapped_column(UTCDateTime)

    operacoes: Mapped[list["OrdemOperacao"]] = relationship(
        back_populates="ordem", order_by="OrdemOperacao.sequencia", cascade="all, delete-orphan"
    )


class OrdemOperacao(Base):
    """Roteiro da ordem: cópia (snapshot) das operações do processo no momento da criação."""

    __tablename__ = "ordem_operacoes"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    ordem_id: Mapped[int] = mapped_column(ForeignKey("ordens.id"), index=True)
    operacao_id: Mapped[int | None] = mapped_column(ForeignKey("operacoes.id"))
    sequencia: Mapped[int] = mapped_column(Integer)
    etapa_nome: Mapped[str] = mapped_column(String(200))
    nome: Mapped[str] = mapped_column(String(200))
    recurso_id: Mapped[int | None] = mapped_column(ForeignKey("recursos.id"))
    qtd_planejada: Mapped[float] = mapped_column(Float)
    formula_tipo: Mapped[str] = mapped_column(String(20), default="linear")
    tempo_prep_est_min: Mapped[float | None] = mapped_column(Float)
    tempo_exec_est_min: Mapped[float | None] = mapped_column(Float)
    fonte_estimativa: Mapped[str] = mapped_column(String(20), default="sem_base")
    amostras: Mapped[int] = mapped_column(Integer, default=0)
    detalhe_estimativa: Mapped[list | None] = mapped_column(JSON)  # elementos do modelo, em minutos
    estimativa_validada: Mapped[bool] = mapped_column(Boolean, default=True)
    opcional: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    iniciada_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    concluida_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    concluida_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    ordem: Mapped[Ordem] = relationship(back_populates="operacoes")


class Apontamento(Base):
    """Registro de tempo/quantidade. Nunca é apagado: apenas anulado com motivo."""

    __tablename__ = "apontamentos"
    __table_args__ = (
        Index("ix_apont_ordem", "empresa_id", "ordem_id"),
        Index("ix_apont_inicio", "empresa_id", "unidade_id", "inicio"),
    )
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    ordem_id: Mapped[int] = mapped_column(ForeignKey("ordens.id"))
    ordem_operacao_id: Mapped[int] = mapped_column(ForeignKey("ordem_operacoes.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="execucao")
    pessoa_id: Mapped[int | None] = mapped_column(ForeignKey("pessoas.id"))
    recurso_id: Mapped[int | None] = mapped_column(ForeignKey("recursos.id"))
    inicio: Mapped[datetime] = mapped_column(UTCDateTime)
    fim: Mapped[datetime | None] = mapped_column(UTCDateTime)
    quantidade_boa: Mapped[float] = mapped_column(Float, default=0)
    quantidade_refugo: Mapped[float] = mapped_column(Float, default=0)
    dados_extras: Mapped[dict] = mapped_column(JSON, default=dict)
    observacao: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="registrado")
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    registrado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    decidido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    decidido_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    anulado_motivo: Mapped[str] = mapped_column(Text, default="")
    anulado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    anulado_em: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Ocorrencia(Base):
    __tablename__ = "ocorrencias"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    ordem_id: Mapped[int | None] = mapped_column(ForeignKey("ordens.id"), index=True)
    ordem_operacao_id: Mapped[int | None] = mapped_column(ForeignKey("ordem_operacoes.id"))
    recurso_id: Mapped[int | None] = mapped_column(ForeignKey("recursos.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    causa: Mapped[str] = mapped_column(String(200), default="")
    descricao: Mapped[str] = mapped_column(Text, default="")
    impacto: Mapped[str] = mapped_column(String(300), default="")
    inicio: Mapped[datetime] = mapped_column(UTCDateTime)
    fim: Mapped[datetime | None] = mapped_column(UTCDateTime)
    registrada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    registrada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    anulada: Mapped[bool] = mapped_column(Boolean, default=False)
    anulada_motivo: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- IA e auditoria
class RecomendacaoIA(Base):
    """Toda saída da IA vira uma sugestão rastreável; nada é aplicado sem aprovação."""

    __tablename__ = "recomendacoes_ia"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    titulo: Mapped[str] = mapped_column(String(300))
    conteudo: Mapped[dict] = mapped_column(JSON, default=dict)
    evidencias: Mapped[dict] = mapped_column(JSON, default=dict)  # fatos calculados pelo sistema
    justificativa: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    provedor: Mapped[str] = mapped_column(String(80), default="heuristica")
    alvo_tipo: Mapped[str | None] = mapped_column(String(30))
    alvo_id: Mapped[int | None] = mapped_column(Integer)
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora)
    decidida_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    decidida_em: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decisao_obs: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    """Trilha append-only. Não há endpoint de alteração ou remoção."""

    __tablename__ = "auditoria"
    id: Mapped[int] = _pk()
    empresa_id: Mapped[int] = _empresa()
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    acao: Mapped[str] = mapped_column(String(60), index=True)
    entidade: Mapped[str] = mapped_column(String(60), index=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer)
    antes: Mapped[dict | None] = mapped_column(JSON)
    depois: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str] = mapped_column(String(64), default="")
    em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora, index=True)
