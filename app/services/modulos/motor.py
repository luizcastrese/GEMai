"""Motor dos módulos: condições → elementos (módulo) → minutos (modelo_tempo.calcular) → hierarquia.

Camadas, na ordem do estudo de tempos: tempo-base dos elementos → ritmo (só o que depende do operador) → TEMPO NORMAL
→ fator de calibração do módulo (multiplicativo, só se validado; padrão 1) → tolerâncias (FT) → TEMPO PADRÃO.
A preparação fica separada da execução. O sistema calcula; ninguém digita tempo, taxa ou % de tolerância.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import modelo_tempo as mt
from .base import EntradaModulo, Modulo
from .coeficientes import VERSAO_CATALOGO

FONTE_OIT = "OIT, Introduction to Work Study (valor único, sem distinção por sexo); conferido em fonte secundária"


def tolerancias_padrao() -> list[dict]:
    """Tolerâncias constantes (necessidades pessoais e fadiga básica). Ponto de partida até as fontes plugáveis da Fase 8."""
    return [{"categoria": "necessidades pessoais", "percentual": mt.REFERENCIAS["tolerancia_pessoal_pct"], "fonte": FONTE_OIT},
            {"categoria": "fadiga básica", "percentual": mt.REFERENCIAS["fadiga_basica_pct"], "fonte": FONTE_OIT}]


@dataclass
class ResultadoModulo:
    modulo: str
    titulo: str
    versao: int
    elementos: list[dict]
    composicao: list[dict] = field(default_factory=list)  # minutos por elemento + linhas de tolerância
    prep: float | None = None  # padrão
    exec: float | None = None  # padrão
    total: float | None = None  # padrão (prep + exec); None = faltam dados
    normal: float | None = None  # prep + exec antes das tolerâncias
    tolerancias: list[dict] = field(default_factory=list)
    ft: float = 1.0
    tolerancia_pct: float = 0.0
    faltantes: list[str] = field(default_factory=list)
    premissas: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    parametros: dict = field(default_factory=dict)
    coeficientes: list[dict] = field(default_factory=list)
    pessoas: int = 1
    fator_calibracao: float = 1.0
    calibrado: bool = False
    normal_base: float | None = None  # prep + exec em ritmo 100, ANTES do fator de calibração (base da calibração)
    fracao_operador: float | None = None  # fração do tempo-base que depende do operador (None = não calculável)

    @property
    def completo(self) -> bool:
        return not self.faltantes and bool(self.elementos)


def calcular_modulo(modulo: Modulo, entrada: EntradaModulo, *, tolerancias: list[dict] | None = None, ritmo_pct: float = 100.0,
                    fator_ambiente: float = 1.0, fator_calibracao: float = 1.0, calibrado: bool = False,
                    calibracao: dict | None = None) -> ResultadoModulo:
    """`calibracao` = {fator, amostras, versao} de uma calibração VALIDADA do módulo (rotula o resultado como `calibrado`)."""
    if calibracao:
        fator_calibracao, calibrado = float(calibracao["fator"]), True
    mo = modulo.montar(entrada)
    tol = tolerancias if tolerancias is not None else tolerancias_padrao()
    pessoas = max(entrada.pessoas, mo.pessoas_minimas or 1)
    r = ResultadoModulo(modulo=modulo.chave, titulo=modulo.titulo, versao=modulo.versao, elementos=mo.elementos,
                        faltantes=list(mo.faltantes), premissas=list(mo.premissas), alertas=list(mo.alertas),
                        parametros=mo.parametros, coeficientes=[c.como_dict() for c in mo.coeficientes], pessoas=pessoas,
                        tolerancias=tol)
    if not mo.elementos:
        if not r.faltantes:
            r.faltantes.append("o módulo não gerou elementos de tempo")
        return r
    ctx = mt.Contexto(quantidade=entrada.quantidade, num_pessoas=pessoas, peso_kg=entrada.peso_max_kg,
                      distancia_m=entrada.distancia_m)
    calc = mt.calcular(mo.elementos, fator_ambiente, ctx, tol, ritmo_pct)
    r.faltantes += calc.faltantes
    if not r.completo:
        return r
    ft, p = mt.fator_tolerancia(tol)
    k = min(max(fator_calibracao, 0.5), 2.0)
    base100 = calc if ritmo_pct == 100.0 else mt.calcular(mo.elementos, fator_ambiente, ctx, tol, 100.0)
    r.normal_base = round((base100.prep + base100.exec) / ft, 3)
    r.fracao_operador = mt.fracao_operador(mo.elementos, ctx).geral
    r.ft, r.tolerancia_pct = ft, round(p * 100, 3)
    r.fator_calibracao, r.calibrado = k, calibrado and k != 1.0
    r.composicao = [{**l, "minutos": round(l["minutos"] * k, 3)} if l.get("minutos") is not None else l for l in calc.elementos]
    r.prep, r.exec = round(calc.prep * k, 3), round(calc.exec * k, 3)
    r.total = round(r.prep + r.exec, 3)
    r.normal = round(r.total / ft, 3)
    if calibracao and k != 1.0:
        r.coeficientes.append({"chave": f"calibracao:{modulo.chave}", "valor": round(k, 4), "unidade": "×",
                               "fonte": f"Calibração validada: mediana de {calibracao['amostras']} amostras aprovadas (v{calibracao['versao']})",
                               "status": "calibrado", "versao": int(calibracao["versao"])})
    return r


# ------------------------------------------------------------------ hierarquia: produto → grupo → módulo → elementos
def hierarquia(produto: str, quantidade: float, passos: list[dict]) -> dict:
    """`passos`: dicts com grupo, modulo, titulo, nome, composicao, tempo_normal_min, tempo_prep_min, tempo_exec_min,
    tempo_padrao_min, pessoas, faltantes. Devolve a árvore com totais (e por unidade do produto)."""
    def soma(xs, k):
        v = [x[k] for x in xs if x.get(k) is not None]
        return round(sum(v), 2) if v else None

    def tolerancia(p):
        return round(sum(l["minutos"] for l in (p.get("composicao") or []) if l.get("tipo") == "tolerancia" and l.get("minutos") is not None), 3)

    def no(xs):
        return {"tempo_normal_min": soma(xs, "tempo_normal_min"), "tolerancias_min": round(sum(tolerancia(x) for x in xs), 2),
                "preparacao_min": soma(xs, "tempo_prep_min"), "execucao_min": soma(xs, "tempo_exec_min"),
                "tempo_padrao_min": soma(xs, "tempo_padrao_min")}

    grupos: dict[str, list[dict]] = {}
    for p in passos:
        grupos.setdefault(p.get("grupo") or "Geral", []).append(p)
    out_grupos = []
    for g, ps in grupos.items():
        mods = [{"modulo": p.get("modulo"), "titulo": p.get("titulo") or p.get("nome"), "passo": p.get("nome"), "pessoas": p.get("pessoas"),
                 **no([p]), "completo": not p.get("faltantes"),
                 "elementos": [l for l in (p.get("composicao") or []) if l.get("tipo") != "tolerancia"],
                 "tolerancias": [l for l in (p.get("composicao") or []) if l.get("tipo") == "tolerancia"]} for p in ps]
        out_grupos.append({"grupo": g, **no(ps), "modulos": mods})
    tot = no(passos)
    n = quantidade or 1.0
    por_un = {k: (round(v / n, 3) if v is not None else None) for k, v in tot.items()}
    return {"produto": produto, "quantidade": quantidade, **tot, "por_unidade_produto": por_un, "grupos": out_grupos}


__all__ = ["ResultadoModulo", "calcular_modulo", "hierarquia", "tolerancias_padrao", "VERSAO_CATALOGO"]
