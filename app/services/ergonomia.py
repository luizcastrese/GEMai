"""Fatores de carga e ergonomia (triagem). NÃO substitui a Análise Ergonômica do Trabalho (NR-17).

Métodos usados e suas fontes:
- NIOSH Revised Lifting Equation (Waters et al., 1993; NIOSH Pub. 94-110): RWL = 23 kg · HM · VM · DM · AM · FM · CM
  e LI = carga / RWL. Tabelas FM e CM conferidas em fontes secundárias (CCOHS, CDC) — conferir com a publicação
  original antes de qualquer avaliação formal.
- Murrell: R = T · (W − S) / (W − 1,5), com W = gasto energético no trabalho e S = limite adotado (kcal/min).
  Os limites S por sexo/jornada variam entre fontes: por isso NÃO há valor embutido; é informado por perfil.
- Limites legais de referência (CLT): art. 198 (60 kg, remoção individual) e art. 390 (mulheres: 20 kg contínuo /
  25 kg ocasional; também aplicado a menores de 18, art. 405 §5º). Vigência e interpretação devem ser confirmadas
  com o SESMT/jurídico; a NR-17 exige que o peso não comprometa saúde e segurança.
- A relação LI → tolerância adicional de fadiga (FADIGA_POR_LI) é uma PREMISSA do sistema, não um valor normativo.
"""
from __future__ import annotations

import math

LC_KG = 23.0

# Frequency Multiplier. Chave: frequência (lifts/min). Valor por duração:
#   "ate_1h": (V<75, V>=75), "1_2h": (V<75, V>=75), "2_8h": (V<75, V>=75)
_FM = {
    0.2: {"ate_1h": (1.00, 1.00), "1_2h": (0.95, 0.95), "2_8h": (0.85, 0.85)},
    0.5: {"ate_1h": (0.97, 0.97), "1_2h": (0.92, 0.92), "2_8h": (0.81, 0.81)},
    1: {"ate_1h": (0.94, 0.94), "1_2h": (0.88, 0.88), "2_8h": (0.75, 0.75)},
    2: {"ate_1h": (0.91, 0.91), "1_2h": (0.84, 0.84), "2_8h": (0.65, 0.65)},
    3: {"ate_1h": (0.88, 0.88), "1_2h": (0.79, 0.79), "2_8h": (0.55, 0.55)},
    4: {"ate_1h": (0.84, 0.84), "1_2h": (0.72, 0.72), "2_8h": (0.45, 0.45)},
    5: {"ate_1h": (0.80, 0.80), "1_2h": (0.60, 0.60), "2_8h": (0.35, 0.35)},
    6: {"ate_1h": (0.75, 0.75), "1_2h": (0.50, 0.50), "2_8h": (0.27, 0.27)},
    7: {"ate_1h": (0.70, 0.70), "1_2h": (0.42, 0.42), "2_8h": (0.22, 0.22)},
    8: {"ate_1h": (0.60, 0.60), "1_2h": (0.35, 0.35), "2_8h": (0.18, 0.18)},
    9: {"ate_1h": (0.52, 0.52), "1_2h": (0.30, 0.30), "2_8h": (0.00, 0.15)},
    10: {"ate_1h": (0.45, 0.45), "1_2h": (0.26, 0.26), "2_8h": (0.00, 0.13)},
    11: {"ate_1h": (0.41, 0.41), "1_2h": (0.00, 0.23), "2_8h": (0.00, 0.00)},
    12: {"ate_1h": (0.37, 0.37), "1_2h": (0.00, 0.21), "2_8h": (0.00, 0.00)},
    13: {"ate_1h": (0.00, 0.34), "1_2h": (0.00, 0.00), "2_8h": (0.00, 0.00)},
    14: {"ate_1h": (0.00, 0.31), "1_2h": (0.00, 0.00), "2_8h": (0.00, 0.00)},
    15: {"ate_1h": (0.00, 0.28), "1_2h": (0.00, 0.00), "2_8h": (0.00, 0.00)},
}
# Coupling Multiplier: (V<75, V>=75)
_CM = {"boa": (1.00, 1.00), "regular": (0.95, 1.00), "ruim": (0.90, 0.90)}

# Premissa do sistema (editável no código): LI → tolerância adicional de fadiga (fração do tempo).
FADIGA_POR_LI = [(1.0, 0.00), (2.0, 0.05), (3.0, 0.10), (math.inf, 0.15)]

LIMITE_CLT_INDIVIDUAL_KG = 60.0
LIMITE_CLT_MULHER_CONTINUO_KG = 20.0
LIMITE_CLT_MULHER_OCASIONAL_KG = 25.0

LIMITE_RUIDO_NR15_DBA = 85.0  # exposição de 8 h (NR-15, Anexo 1)


def _fm(freq: float, duracao: str, v_cm: float) -> float:
    """Conservador: usa a linha tabelada de frequência igual ou imediatamente superior."""
    if freq > 15:
        return 0.0
    linha = next(f for f in sorted(_FM) if f >= freq)
    return _FM[linha][duracao][0 if v_cm < 75 else 1]


def niosh(lev: dict | None, carga_kg: float | None) -> dict:
    """Retorna RWL e LI; `completo=False` (e sem número) se faltar alguma entrada."""
    lev = lev or {}
    obrig = {"h_cm": "distância horizontal da carga (H)", "v_cm": "altura vertical da pega (V)",
             "d_cm": "deslocamento vertical (D)", "a_graus": "ângulo de assimetria (A)",
             "freq_por_min": "frequência de levantamentos por minuto", "duracao": "duração do trabalho",
             "pega": "qualidade da pega"}
    falta = [d for k, d in obrig.items() if lev.get(k) in (None, "")]
    carga = lev.get("carga_kg") if lev.get("carga_kg") is not None else carga_kg
    if carga is None:
        falta.append("peso da carga")
    if falta:
        return {"completo": False, "faltantes": falta}
    h, v, d, a = lev["h_cm"], lev["v_cm"], lev["d_cm"], lev["a_graus"]
    hm = 1.0 if h < 25 else (0.0 if h > 63 else 25.0 / h)
    vm = 0.0 if v > 175 else 1 - 0.003 * abs(v - 75)
    dm = 1.0 if d < 25 else (0.0 if d > 175 else 0.82 + 4.5 / d)
    am = 0.0 if a > 135 else 1 - 0.0032 * a
    fm = _fm(lev["freq_por_min"], lev["duracao"], v)
    cm = _CM[lev["pega"]][0 if v < 75 else 1]
    rwl = LC_KG * hm * vm * dm * am * fm * cm
    li = math.inf if rwl <= 0 else carga / rwl
    return {"completo": True, "faltantes": [], "carga_kg": carga, "rwl_kg": round(rwl, 2),
            "li": None if li == math.inf else round(li, 2), "li_infinito": li == math.inf,
            "multiplicadores": {"HM": round(hm, 3), "VM": round(vm, 3), "DM": round(dm, 3),
                                "AM": round(am, 3), "FM": fm, "CM": cm},
            "leitura": ("LI ≤ 1: risco aceitável para a maioria" if li <= 1 else
                        "LI entre 1 e 3: risco aumentado; reprojetar/mitigar" if li <= 3 else
                        "LI > 3: risco elevado; ação necessária"),
            "aviso": "Triagem pelo método NIOSH. A avaliação formal (AET, NR-17) cabe a profissional competente."}


def tolerancia_por_li(li: float | None, infinito: bool = False) -> float:
    if infinito:
        return FADIGA_POR_LI[-1][1]
    for limite, p in FADIGA_POR_LI:
        if li is not None and li <= limite:
            return p
    return FADIGA_POR_LI[-1][1]


def murrell_fracao_descanso(trabalho_kcal_min: float | None, limite_kcal_min: float | None) -> float:
    """Fração de descanso sobre o tempo de trabalho: R/T = (W − S)/(W − 1,5). Zero se W ≤ S."""
    if not trabalho_kcal_min or not limite_kcal_min or trabalho_kcal_min <= limite_kcal_min or trabalho_kcal_min <= 1.5:
        return 0.0
    return (trabalho_kcal_min - limite_kcal_min) / (trabalho_kcal_min - 1.5)


def alertas_carga(carga_kg: float | None, perfil, duracao: str | None) -> list[str]:
    """Referências legais de carga (a verificar). Sexo/idade do perfil só entram aqui — nunca no ritmo."""
    if not carga_kg:
        return []
    out = []
    if carga_kg > LIMITE_CLT_INDIVIDUAL_KG:
        out.append(f"Carga de {carga_kg:g} kg acima de {LIMITE_CLT_INDIVIDUAL_KG:g} kg (CLT art. 198, remoção individual): usar meio mecânico/mais pessoas.")
    if perfil is not None and (perfil.sexo == "feminino" or perfil.faixa_etaria == "menor_18"):
        lim = LIMITE_CLT_MULHER_CONTINUO_KG if duracao in ("2_8h", None) else LIMITE_CLT_MULHER_OCASIONAL_KG
        if carga_kg > lim:
            out.append(f"Carga de {carga_kg:g} kg acima da referência de {lim:g} kg para o perfil (CLT arts. 390/405 §5º; NR-17 exige peso "
                       "compatível com a saúde). Confirmar a norma aplicável com o SESMT/jurídico.")
    return out


def avaliar_operacao(op, perfil, espacos: list, carga_item_kg: float | None) -> dict:
    """Resumo ergonômico de uma operação, usado na prontidão, no endpoint e no modelo de tempo."""
    n = niosh(op.levantamento, carga_item_kg)
    alertas: list[str] = []
    tol: list[dict] = []
    if n.get("completo"):
        p = tolerancia_por_li(n["li"], n["li_infinito"])
        if p > 0:
            tol.append({"categoria": "fadiga por carga (LI)", "percentual": round(p * 100, 2),
                        "justificativa": f"LI = {n['li']}: acima do recomendado pelo NIOSH.",
                        "fonte": "premissa do sistema (LI→tolerância); calibrar com medições"})
        if n["li_infinito"] or n["li"] > 1:
            alertas.append(f"Índice de levantamento {'∞' if n['li_infinito'] else n['li']} > 1: reprojetar (ajuda mecânica, dividir carga, aproximar da altura de pega) e avaliar via AET.")
    alertas += alertas_carga((op.levantamento or {}).get("carga_kg") or carga_item_kg, perfil, (op.levantamento or {}).get("duracao"))
    if perfil is not None and op.gasto_energetico_kcal_min and perfil.limite_energetico_kcal_min:
        r = murrell_fracao_descanso(op.gasto_energetico_kcal_min, perfil.limite_energetico_kcal_min)
        if r > 0:
            tol.append({"categoria": "descanso por gasto energético (Murrell)", "percentual": round(r / (1 + r) * 100, 2),
                        "justificativa": f"W={op.gasto_energetico_kcal_min:g} kcal/min acima do limite adotado S={perfil.limite_energetico_kcal_min:g}.",
                        "fonte": "Murrell: R=T(W−S)/(W−1,5)"})
    if perfil is not None and op.altura_trabalho_m and perfil.altura_cotovelo_cm:
        dif = round(op.altura_trabalho_m * 100 - perfil.altura_cotovelo_cm, 1)
        alertas.append(f"Altura de trabalho {abs(dif):g} cm {'acima' if dif > 0 else 'abaixo'} da altura do cotovelo do perfil — "
                       "compare com a faixa recomendada para o tipo de trabalho (as fontes divergem: trabalho pesado abaixo do cotovelo, de precisão acima).")
    vistos = set()
    for e in espacos:
        if e is None or e.id in vistos:
            continue
        vistos.add(e.id)
        if e.ruido_db and e.ruido_db > LIMITE_RUIDO_NR15_DBA:
            alertas.append(f"Ruído de {e.ruido_db:g} dB(A) em '{e.nome}' acima de {LIMITE_RUIDO_NR15_DBA:g} dB(A) (NR-15, 8 h): avaliar exposição e tolerância.")
    return {"niosh": n, "alertas": alertas, "tolerancias_sugeridas": tol}
