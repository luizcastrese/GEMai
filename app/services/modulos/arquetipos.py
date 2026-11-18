"""Arquétipos de cálculo: o motor GENÉRICO que transforma a especificação de um módulo (DADO) em elementos de tempo.

Toda atividade produtiva, de qualquer segmento, combina mão de obra + atividade + equipamento + espaço + item. O tempo de
cada atividade cai em uma de poucas FORMAS de cálculo, cada uma com base na Engenharia de Produção:

| Arquétipo            | Forma                                                         | Base                                         |
|----------------------|---------------------------------------------------------------|----------------------------------------------|
| processamento_meio   | Σ driver ÷ taxa da ficha técnica do meio (+ manuseio + preparo)| dados de processo (tempo de máquina)         |
| manual               | Σ driver × sequência de movimentos (TMU)                       | tempos predeterminados (sequência MOST)      |
| deslocamento         | viagens × distância ÷ velocidade                               | movimentação de materiais                    |
| espera               | tempo de ciclo da ficha técnica do meio (cura, secagem…)       | parâmetro técnico do processo                |

Um módulo da empresa é uma `EspecModulo`: arquétipo + fórmula do *driver* sobre os atributos da peça (área, comprimento, peso,
quantidade ou qualquer atributo livre) + parâmetros da ficha técnica + ações manuais de vocabulário FECHADO. Ninguém escreve
minutos: a IA (ou a pessoa) escolhe o arquétipo e as categorias; o sistema calcula. Uma especificação só entra no cálculo
depois de VALIDADA por uma pessoa.

Os índices de movimento abaixo são ILUSTRATIVOS (inspirados na Sequência de Movimento Geral do BasicMOST, A B G A B P A,
índices 0/1/3/6/10/16) e rotulados como referência genérica: devem ser conferidos no cartão certificado ou substituídos pela
calibração com o tempo real medido. Não reproduzem tabelas licenciadas.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .. import formulas as fm
from .. import modelo_tempo as mt
from .base import EntradaModulo, Modulo, Montagem, ParametroModulo, el
from .coeficientes import Coeficiente, coef

Arquetipo = Literal["processamento_meio", "manual", "deslocamento", "espera"]
ARQUETIPOS: tuple[str, ...] = Arquetipo.__args__

# ------------------------------------------------------------------ vocabulário fechado de movimentos (TMU ilustrativos)
ALCANCE = {"ao_alcance": 1, "1_2_passos": 3, "3_4_passos": 6, "5_7_passos": 10}          # A: distância da ação
CORPO = {"nenhum": 0, "curvar_parcial": 3, "curvar_levantar": 6, "sentar_levantar": 10}   # B: movimento do corpo
PEGAR = {"leve": 1, "pesado_ou_preso": 3}                                                   # G: obter o objeto
POSICIONAR = {"soltar": 0, "aproximado": 1, "ajuste_leve": 3, "ajuste_preciso": 6}          # P: colocar
Alcance = Literal["ao_alcance", "1_2_passos", "3_4_passos", "5_7_passos"]
Corpo = Literal["nenhum", "curvar_parcial", "curvar_levantar", "sentar_levantar"]
Pegar = Literal["leve", "pesado_ou_preso"]
Posicionar = Literal["soltar", "aproximado", "ajuste_leve", "ajuste_preciso"]
FONTE_MOVIMENTOS = ("Índices MOST ILUSTRATIVOS (Sequência de Movimento Geral A B G A B P A, inspirada no BasicMOST); conferir com o "
                    "cartão certificado ou calibrar com o tempo real. 1 TMU = 0,0006 min")

# Campos que toda peça oferece à fórmula do driver (além dos atributos livres da peça).
CAMPOS_PECA = {"qtd": "quantidade da peça por unidade do produto", "comp": "comprimento (m)", "larg": "largura (m)", "esp": "espessura (m)",
               "peso_kg": "peso (kg)", "furos": "furos", "bordas_m": "metros de borda", "area_m2": "área = comp × larg (m²)",
               "perimetro_m": "perímetro = 2 × (comp + larg) (m)", "volume_m3": "volume = comp × larg × esp (m³)", "unidade": "1 (uma vez)"}

_CHAVE = re.compile(r"^[a-z][a-z0-9_]{1,29}$")
_PARAM = re.compile(r"^[a-z][a-z0-9_]{2,59}$")


class AcaoManual(BaseModel):
    """Uma ação manual = uma Sequência de Movimento Geral, escolhida por categorias (nunca por minutos)."""

    nome: str = Field(min_length=1, max_length=120)
    alcance: Alcance = "ao_alcance"          # A: até o objeto
    corpo: Corpo = "nenhum"                  # B: ao pegar
    pegar: Pegar = "leve"                    # G
    levar: Alcance = "ao_alcance"            # A: com o objeto até o destino
    corpo_destino: Corpo = "nenhum"          # B: ao colocar
    posicionar: Posicionar = "aproximado"    # P
    retorno: Alcance | Literal["nenhum"] = "nenhum"  # A: volta

    def indices(self) -> list[int]:
        return [ALCANCE[self.alcance], CORPO[self.corpo], PEGAR[self.pegar], ALCANCE[self.levar], CORPO[self.corpo_destino],
                POSICIONAR[self.posicionar], 0 if self.retorno == "nenhum" else ALCANCE[self.retorno]]

    def minutos(self) -> float:
        return sum(self.indices()) * 10 * mt.TMU_MIN


class ParametroTecnico(BaseModel):
    """Parâmetro da FICHA TÉCNICA do meio que o módulo usa (característica do equipamento, validada por pessoa)."""

    nome: str = Field(min_length=3, max_length=60)  # ex.: taxa_lixamento_m2_min
    unidade: str = Field(min_length=1, max_length=20)  # ex.: m²/min, un/min, min
    descricao: str = Field(min_length=1, max_length=200)
    minimo: float = Field(gt=0)
    maximo: float = Field(gt=0)

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        if not _PARAM.match(v):
            raise ValueError("nome do parâmetro: minúsculas, números e _ (ex.: taxa_lixamento_m2_min)")
        return v


class EspecModulo(BaseModel):
    """Especificação de um módulo (DADO). Nenhum campo é tempo digitado."""

    chave: str
    titulo: str = Field(min_length=1, max_length=120)
    descricao: str = Field("", max_length=1000)
    arquetipo: Arquetipo
    tipo_passo: str = Field("processamento", min_length=1, max_length=30)  # rótulo do passo no plano
    unidade_contagem: Literal["peca", "unidade_produto"] = "peca"
    driver: str = Field("{qtd}", max_length=200)  # fórmula por peça (sem "="), sobre CAMPOS_PECA e atributos livres
    unidade_driver: str = Field("un", max_length=20)
    funcao_meio: str = Field("", max_length=40)  # função do meio que executa (para o planejador e a checagem da oficina)
    taxa: ParametroTecnico | None = None  # processamento_meio: unidades do driver por minuto; espera: minutos do ciclo
    preparacao: Literal["maquina", "posto", "nenhuma"] = "nenhuma"
    acoes: list[AcaoManual] = Field(default_factory=list, max_length=12)  # manual: por unidade do driver; processamento: manuseio por peça
    premissas: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("chave")
    @classmethod
    def _chave(cls, v: str) -> str:
        if not _CHAVE.match(v):
            raise ValueError("chave: 2 a 30 caracteres, minúsculas, números e _")
        return v

    @field_validator("driver")
    @classmethod
    def _driver(cls, v: str) -> str:
        v = (v or "").strip().lstrip("=") or "{qtd}"
        fm.compilar(v)  # FormulaErro (ValueError) com mensagem em português
        return v

    def problemas(self) -> list[str]:
        """O que impede a especificação de calcular (coerência entre arquétipo e campos)."""
        p = []
        if self.arquetipo in ("processamento_meio", "espera") and self.taxa is None:
            p.append("falta o parâmetro técnico da ficha do meio (taxa ou tempo de ciclo)")
        if self.taxa is not None and self.taxa.minimo > self.taxa.maximo:
            p.append("faixa plausível do parâmetro técnico invertida")
        if self.arquetipo == "manual" and not self.acoes:
            p.append("o módulo manual precisa de ao menos uma ação (sequência de movimentos)")
        return p


# ------------------------------------------------------------------ construção do Módulo a partir da especificação
def _campos(c: dict) -> dict:
    comp, larg, esp = c.get("comp"), c.get("larg"), c.get("esp")
    v = {k: c.get(k) for k in ("qtd", "comp", "larg", "esp", "peso_kg", "furos", "bordas_m")}
    v["area_m2"] = comp * larg if comp and larg else None
    v["perimetro_m"] = 2 * (comp + larg) if comp and larg else None
    v["volume_m3"] = comp * larg * esp if comp and larg and esp else None
    v["unidade"] = 1.0
    for k, x in (c.get("atributos") or {}).items():
        v.setdefault(str(k).casefold(), x)
    return {k: x for k, x in v.items() if x is not None}


def _driver_total(espec: EspecModulo, e: EntradaModulo, m: Montagem) -> float | None:
    """Σ driver(peça) × quantidade total da peça. Campo ausente vira pendência, nunca zero."""
    arvore = fm.compilar(espec.driver)
    if not e.componentes:
        if fm.campos_usados(arvore) - {"unidade"}:
            m.faltantes.append("nenhuma peça neste passo para medir o driver")
            return None
        return fm.avaliar(arvore, {"unidade": 1.0}) * e.quantidade
    total, ok = 0.0, True
    por_produto = espec.unidade_contagem == "unidade_produto"
    for c in e.componentes:
        try:
            v = fm.avaliar(arvore, _campos(c))
        except fm.FaltaValor as f:
            m.faltantes.append(f"falta '{f}' de '{c['nome']}' (usado em {espec.driver})")
            ok = False
            continue
        except fm.FormulaErro as f:
            m.faltantes.append(f"driver de '{c['nome']}': {f}")
            ok = False
            continue
        total += max(v, 0.0) * (c.get("qtd") or 1.0) * e.unidades_produto
    if por_produto and total == 0 and ok:
        total = e.unidades_produto
    return total if ok else None


def _coef_acao(a: AcaoManual) -> Coeficiente:
    return Coeficiente(f"movimento:{a.nome[:40]}", round(a.minutos(), 5), "min/ação", FONTE_MOVIMENTOS)


def _preparo(espec: EspecModulo, e: EntradaModulo, m: Montagem) -> None:
    if espec.preparacao == "nenhuma":
        return
    c = coef("preparacao_maquina_min" if espec.preparacao == "maquina" else "preparacao_posto_min")
    m.coeficientes.append(c)
    m.elementos.append(el(f"Preparar {e.recurso_nome or 'o posto'}", "preparacao", "fixo", a_min=c.valor,
                          justificativa="Referência genérica de preparação do catálogo; calibre com o histórico."))


def _taxa(espec: EspecModulo, e: EntradaModulo, m: Montagem) -> float | None:
    t = espec.taxa
    if not e.recurso_nome:
        m.faltantes.append("falta o equipamento deste passo (cadastre e escolha um meio)")
        return None
    v = e.ficha.get(t.nome)
    m.parametros[t.nome] = v
    if not v:
        m.faltantes.append(f"falta '{t.descricao}' ({t.nome}, {t.unidade}) na ficha técnica de '{e.recurso_nome}'")
        return None
    return v


def montar_por_espec(espec: EspecModulo, e: EntradaModulo) -> Montagem:
    m = Montagem(premissas=list(espec.premissas))
    m.faltantes += espec.problemas()
    if m.faltantes:
        return m
    if espec.arquetipo == "deslocamento":
        from . import movimentacao
        r = movimentacao.montar(e)
        r.premissas = list(espec.premissas) + r.premissas
        return r
    driver = _driver_total(espec, e, m)
    m.parametros.update(driver=espec.driver, unidade_driver=espec.unidade_driver, quantidade_driver=round(driver, 4) if driver is not None else None)
    if espec.arquetipo == "processamento_meio":
        taxa = _taxa(espec, e, m)
        if driver is None or taxa is None:
            return m
        _preparo(espec, e, m)
        m.elementos.append(el(f"{espec.titulo} em {e.recurso_nome}", "processamento", "fixo", a_min=driver / taxa, depende_operador=False,
                              justificativa=f"{driver:g} {espec.unidade_driver} ÷ {taxa:g} {espec.taxa.unidade} (ficha técnica)."))
        pecas = sum((c.get("qtd") or 1.0) for c in e.componentes) * e.unidades_produto if e.componentes else e.quantidade
        for a in espec.acoes:  # alimentar/retirar: manual, por peça
            c = _coef_acao(a)
            m.coeficientes.append(c)
            m.elementos.append(el(f"{a.nome} ({pecas:g} peça(s))", "manuseio", "fixo", a_min=round(pecas * c.valor, 4),
                                  justificativa=f"≈{c.valor * 60:.1f} s por peça (sequência de movimentos ilustrativa)."))
        if not espec.acoes:
            m.premissas.append("Alimentação e retirada manual das peças não foram descritas neste módulo.")
    elif espec.arquetipo == "manual":
        if driver is None:
            return m
        _preparo(espec, e, m)
        por_un = 0.0
        for a in espec.acoes:
            c = _coef_acao(a)
            m.coeficientes.append(c)
            por_un += c.valor
        nomes = ", ".join(a.nome for a in espec.acoes)
        m.elementos.append(el(f"{espec.titulo}: {nomes}", "manuseio", "fixo", a_min=round(driver * por_un, 4), paralelizavel=True,
                              justificativa=f"{driver:g} {espec.unidade_driver} × {por_un * 60:.1f} s (sequência de movimentos ilustrativa)."))
        pessoas = e.pessoas
        if pessoas > 1:
            m.premissas.append(f"{espec.titulo}: trabalho manual dividido por igual entre {pessoas} pessoas (caso ideal).")
    elif espec.arquetipo == "espera":
        ciclo = _taxa(espec, e, m)
        if ciclo is None:
            return m
        lotes = 1
        m.parametros["ciclos"] = lotes
        m.elementos.append(el(f"{espec.titulo} ({e.recurso_nome})", "processamento", "fixo", a_min=ciclo, depende_operador=False,
                              justificativa=f"Tempo de ciclo de {ciclo:g} min (ficha técnica); ninguém fica parado esperando."))
        m.premissas.append(f"{espec.titulo}: um ciclo por pedido (o lote inteiro cabe no equipamento).")
    return m


def construir(espec: EspecModulo, versao: int = 1) -> Modulo:
    """Módulo executável a partir da especificação."""
    params = [ParametroModulo("driver", espec.unidade_driver, f"Quantidade do driver: {espec.driver}", "produto")]
    if espec.taxa is not None:
        params.append(ParametroModulo(espec.taxa.nome, espec.taxa.unidade, espec.taxa.descricao, "meio"))
    precisa = espec.arquetipo in ("processamento_meio", "espera")
    return Modulo(chave=espec.chave, titulo=espec.titulo, tipo_passo=espec.tipo_passo, unidade_contagem=espec.unidade_contagem,
                  parametros=tuple(params), montar=lambda e: montar_por_espec(espec, e), versao=versao, precisa_recurso=precisa,
                  descricao=espec.descricao or espec.titulo, arquetipo=espec.arquetipo, funcao_meio=espec.funcao_meio,
                  pacote="empresa", driver=espec.driver)


def vocabulario() -> dict:
    """O que a IA (e a tela) pode escolher. Nenhum minuto aparece aqui: só categorias."""
    return {"arquetipos": list(ARQUETIPOS), "alcance": list(ALCANCE), "corpo": list(CORPO), "pegar": list(PEGAR),
            "posicionar": list(POSICIONAR), "campos_peca": CAMPOS_PECA, "preparacao": ["maquina", "posto", "nenhuma"]}


def slug(texto: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s or not s[0].isalpha():
        s = "m_" + s
    return s[:30].rstrip("_") or "modulo"


__all__ = ["EspecModulo", "AcaoManual", "ParametroTecnico", "ARQUETIPOS", "construir", "montar_por_espec", "vocabulario", "slug"]
