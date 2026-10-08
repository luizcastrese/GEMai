"""Modelo de tempo (gêmeo digital): a IA propõe elementos; o SISTEMA calcula.

Segurança e consistência: os elementos usam um vocabulário FECHADO de métodos. Nada que
a IA escreva é executado como código. Se um dado do contorno físico necessário ao cálculo
não existe (distância, peso, capacidade…), o elemento NÃO vira zero: o resultado é marcado
como incompleto e o dado faltante é listado.

Métodos:
- fixo               t = a · (qtd se por_unidade)
- linear_driver      t = (a + b · driver) · (qtd se por_unidade)       driver ∈ peso_kg, area_m2, comprimento_m, volume_m3, distancia_m
- deslocamento       t = ceil(qtd / itens_por_viagem) · distancia / velocidade · (2 se ida_e_volta)
- capacidade_recurso t = qtd / capacidade(un/h) · 60
Elementos `paralelizavel` são divididos pelo nº de pessoas. O total é multiplicado por `fator_ambiente`.
Elementos do tipo `preparacao` compõem o tempo de preparação; os demais, o de execução.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

TIPOS = ("preparacao", "deslocamento", "manuseio", "processamento", "inspecao", "espera_fixa", "outro")
METODOS = ("fixo", "linear_driver", "deslocamento", "capacidade_recurso")
DRIVERS = ("nenhum", "peso_kg", "area_m2", "comprimento_m", "volume_m3", "distancia_m")

# Referências genéricas usadas SÓ pelo provedor local; sempre declaradas nas premissas, confiança baixa.
REFERENCIAS = {
    "velocidade_caminhada_m_min": 75.0,
    "carga_manual_max_kg": 20.0,
    "manuseio_base_min": 0.15,
    "manuseio_min_por_kg": 0.012,
    "preparacao_maquina_min": 5.0,
    "preparacao_posto_min": 2.0,
}


class ElementoTempo(BaseModel):
    nome: str
    tipo: Literal["preparacao", "deslocamento", "manuseio", "processamento", "inspecao", "espera_fixa", "outro"] = "outro"
    metodo: Literal["fixo", "linear_driver", "deslocamento", "capacidade_recurso"] = "fixo"
    por_unidade: bool = False
    driver: Literal["nenhum", "peso_kg", "area_m2", "comprimento_m", "volume_m3", "distancia_m"] = "nenhum"
    a_min: float = 0.0
    b_min: float = 0.0
    velocidade_m_min: float | None = None
    itens_por_viagem: float | None = None
    ida_e_volta: bool = True
    paralelizavel: bool = False
    justificativa: str = ""


class ModeloTempoIA(BaseModel):
    """Saída esperada da IA (e do provedor local)."""

    elementos: list[ElementoTempo] = Field(default_factory=list)
    fator_ambiente: float = 1.0
    premissas: list[str] = Field(default_factory=list)
    dados_faltantes: list[str] = Field(default_factory=list)
    padrao_apontamento_inicio: str = ""
    padrao_apontamento_fim: str = ""
    unidade_contagem: str = ""
    confianca: Literal["baixa", "media", "alta"] = "baixa"
    justificativa: str = ""


def _t(s: str | None, n: int) -> str:
    return (s or "").replace("\x00", "").strip()[:n]


def _num(v: float | None, lo: float, hi: float, padrao: float | None = None) -> float | None:
    if v is None or isinstance(v, bool) or v != v or v in (math.inf, -math.inf):
        return padrao
    return min(max(float(v), lo), hi)


def sanear_modelo(m: ModeloTempoIA) -> ModeloTempoIA:
    """Limites de tamanho e de valores; descarta elementos sem sentido."""
    els = []
    for e in m.elementos[:15]:
        if not _t(e.nome, 200):
            continue
        els.append(ElementoTempo(
            nome=_t(e.nome, 200), tipo=e.tipo, metodo=e.metodo, por_unidade=e.por_unidade, driver=e.driver,
            a_min=_num(e.a_min, 0, 100_000, 0.0), b_min=_num(e.b_min, 0, 100_000, 0.0),
            velocidade_m_min=_num(e.velocidade_m_min, 1, 500, None), itens_por_viagem=_num(e.itens_por_viagem, 0.01, 100_000, None),
            ida_e_volta=e.ida_e_volta, paralelizavel=e.paralelizavel, justificativa=_t(e.justificativa, 500)))
    return ModeloTempoIA(
        elementos=els, fator_ambiente=_num(m.fator_ambiente, 0.5, 3.0, 1.0),
        premissas=[_t(x, 400) for x in m.premissas[:20] if _t(x, 400)],
        dados_faltantes=[_t(x, 300) for x in m.dados_faltantes[:20] if _t(x, 300)],
        padrao_apontamento_inicio=_t(m.padrao_apontamento_inicio, 300), padrao_apontamento_fim=_t(m.padrao_apontamento_fim, 300),
        unidade_contagem=_t(m.unidade_contagem, 60), confianca=m.confianca, justificativa=_t(m.justificativa, 3000))


# ---------------------------------------------------------------- contexto físico
@dataclass
class Contexto:
    quantidade: float = 1.0
    num_pessoas: int = 1
    peso_kg: float | None = None
    comprimento_m: float | None = None
    largura_m: float | None = None
    altura_m: float | None = None
    distancia_m: float | None = None
    capacidade_un_h: float | None = None

    @property
    def area_m2(self):
        return self.comprimento_m * self.largura_m if self.comprimento_m and self.largura_m else None

    @property
    def volume_m3(self):
        a = self.area_m2
        return a * self.altura_m if a and self.altura_m else None

    def driver(self, nome: str) -> float | None:
        return {"nenhum": 0.0, "peso_kg": self.peso_kg, "area_m2": self.area_m2, "comprimento_m": self.comprimento_m,
                "volume_m3": self.volume_m3, "distancia_m": self.distancia_m}[nome]


def capacidade_por_hora(valor: float | None, unidade: str) -> float | None:
    """Normaliza capacidade para unidades/hora; None se a unidade não for de taxa."""
    if not valor or valor <= 0:
        return None
    u = (unidade or "").lower().replace(" ", "")
    if u.endswith(("/h", "/hora", "porhora")):
        return valor
    if u.endswith(("/min", "/minuto")):
        return valor * 60
    if u.endswith(("/dia",)):
        return None  # depende do turno: não assumir
    return None


def distancia_entre(db: Session, empresa_id: int, a: int | None, b: int | None) -> float | None:
    from ..models import Distancia
    if not a or not b:
        return None
    if a == b:
        return 0.0
    d = db.scalar(select(Distancia.metros).where(
        Distancia.empresa_id == empresa_id,
        ((Distancia.origem_id == a) & (Distancia.destino_id == b)) | ((Distancia.origem_id == b) & (Distancia.destino_id == a))))
    return d


def montar_contexto(db: Session, empresa_id: int, operacao, quantidade: float, produto=None, recurso=None) -> Contexto:
    """Contorno físico efetivo: item típico da operação, sobreposto pelo produto da ordem."""
    c = Contexto(quantidade=quantidade, num_pessoas=max(operacao.num_pessoas or 1, 1))
    for campo, op_campo in (("peso_kg", "item_peso_kg"), ("comprimento_m", "item_comprimento_m"),
                            ("largura_m", "item_largura_m"), ("altura_m", "item_altura_m")):
        v = getattr(produto, campo, None) if produto is not None else None
        setattr(c, campo, v if v is not None else getattr(operacao, op_campo))
    c.distancia_m = operacao.distancia_m if operacao.distancia_m is not None else distancia_entre(
        db, empresa_id, operacao.espaco_origem_id, operacao.espaco_destino_id)
    rec = recurso
    if rec is None and operacao.recurso_padrao_id:
        from ..models import Recurso
        rec = db.get(Recurso, operacao.recurso_padrao_id)
    if rec is not None:
        c.capacidade_un_h = capacidade_por_hora(rec.capacidade, rec.capacidade_unidade)
    return c


# ---------------------------------------------------------------- cálculo
@dataclass
class Resultado:
    prep: float = 0.0
    exec: float = 0.0
    elementos: list[dict] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    fator_ambiente: float = 1.0

    @property
    def completo(self) -> bool:
        return not self.faltantes and bool(self.elementos)


def _elemento(e: dict, c: Contexto) -> tuple[float | None, str | None]:
    q = c.quantidade
    m = e["metodo"]
    if m == "fixo":
        t = e["a_min"] * (q if e["por_unidade"] else 1)
    elif m == "linear_driver":
        dv = c.driver(e["driver"])
        if dv is None:
            return None, f"'{e['nome']}': falta {e['driver']} do item/ambiente"
        t = (e["a_min"] + e["b_min"] * dv) * (q if e["por_unidade"] else 1)
    elif m == "deslocamento":
        if c.distancia_m is None:
            return None, f"'{e['nome']}': falta a distância entre os espaços de origem e destino"
        vel = e.get("velocidade_m_min")
        if not vel or vel <= 0:
            return None, f"'{e['nome']}': velocidade de deslocamento não definida"
        viagens = math.ceil(q / max(e.get("itens_por_viagem") or 1.0, 1e-9))
        t = viagens * (c.distancia_m / vel) * (2 if e.get("ida_e_volta", True) else 1)
    elif m == "capacidade_recurso":
        if not c.capacidade_un_h:
            return None, f"'{e['nome']}': falta a capacidade (un/h) do equipamento"
        t = q / c.capacidade_un_h * 60
    else:
        return None, f"'{e['nome']}': método desconhecido"
    if e.get("paralelizavel"):
        t /= max(c.num_pessoas, 1)
    return t, None


def calcular(elementos: list[dict], fator_ambiente: float, c: Contexto) -> Resultado:
    r = Resultado(fator_ambiente=fator_ambiente)
    f = min(max(fator_ambiente or 1.0, 0.5), 3.0)
    for e in elementos:
        t, falta = _elemento(e, c)
        if falta:
            r.faltantes.append(falta)
            r.elementos.append({"nome": e["nome"], "tipo": e["tipo"], "minutos": None, "motivo": falta})
            continue
        t *= f
        r.elementos.append({"nome": e["nome"], "tipo": e["tipo"], "minutos": round(t, 3)})
        if e["tipo"] == "preparacao":
            r.prep += t
        else:
            r.exec += t
    r.prep, r.exec = round(r.prep, 3), round(r.exec, 3)
    return r


def modelo_ativo(db: Session, empresa_id: int, operacao_id: int):
    """Versão mais recente não rejeitada."""
    from ..models import ModeloTempo
    return db.scalar(select(ModeloTempo).where(
        ModeloTempo.empresa_id == empresa_id, ModeloTempo.operacao_id == operacao_id,
        ModeloTempo.status_validacao != "rejeitado").order_by(ModeloTempo.versao.desc()).limit(1))
