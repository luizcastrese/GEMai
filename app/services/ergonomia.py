"""Fatores de carga e ergonomia (triagem). NÃO substitui a Análise Ergonômica do Trabalho (NR-17).

Métodos usados e suas fontes:
- NIOSH (Pub. 94-110): a constante de carga LC = 23 kg (condições ideais) é usada como referência de carga para perfil masculino adulto.
- Murrell: R = T · (W − S) / (W − 1,5), com W = gasto energético no trabalho e S = limite adotado (kcal/min).
  Os limites S por sexo/jornada variam entre fontes: por isso NÃO há valor embutido; é informado por perfil.
- Limites legais de referência (CLT): art. 198 (60 kg, remoção individual) e art. 390 (mulheres: 20 kg contínuo /
  25 kg ocasional; também aplicado a menores de 18, art. 405 §5º). Vigência e interpretação devem ser confirmadas
  com o SESMT/jurídico; a NR-17 exige que o peso não comprometa saúde e segurança.
"""
from __future__ import annotations

LC_KG = 23.0
LIMITE_CLT_INDIVIDUAL_KG = 60.0
LIMITE_CLT_MULHER_CONTINUO_KG = 20.0
LIMITE_CLT_MULHER_OCASIONAL_KG = 25.0

LIMITE_RUIDO_NR15_DBA = 85.0  # exposição de 8 h (NR-15, Anexo 1)


# ---------------------------------------------------------------------------------------------------------------
# Antropometria → ergonomia → tempo (plano de trabalho).
# Sexo, estatura e peso corporal NÃO são multiplicadores de produtividade (o ritmo é calibrado por medição). Eles
# entram no tempo SÓ por mecanismos ergonômicos, todos declarados nas premissas do plano:
#   1. altura da bancada × altura do cotovelo → postura → tolerância de fadiga;
#   2. limite de carga manual do perfil → quantas pessoas e quantas peças por viagem;
#   3. gasto energético (MET × peso corporal) acima do limite informado → descanso de Murrell.
# Os coeficientes abaixo são PREMISSAS do sistema (fontes divergem): calibre com medições e com o SESMT.
# ---------------------------------------------------------------------------------------------------------------
ALTURA_COTOVELO_FRACAO = 0.63  # altura do cotovelo ≈ 63 % da estatura (proporção antropométrica clássica)
# Faixa recomendada da superfície de trabalho em relação ao cotovelo, em cm (negativo = abaixo do cotovelo).
FAIXA_ALTURA_CM = {"montagem": (-15.0, 0.0), "inspecao": (-5.0, 10.0)}
TOLERANCIA_ALTURA_PCT_POR_CM = 0.4  # % de fadiga adicional por cm fora da faixa
TOLERANCIA_ALTURA_MAX_PCT = 8.0
CARGA_REF_RESTRITIVA_KG = 20.0  # CLT art. 390/405: mulheres e menores (contínuo); também adotado para equipe mista ou perfil não informado
CARGA_REF_ADULTO_MASCULINO_KG = 23.0  # NIOSH LC (condições ideais); premissa para perfil masculino adulto
MET_REFERENCIA = {"movimentacao": 4.0, "montagem": 3.5, "inspecao": 2.0}  # genéricos e ilustrativos (tipo Compendium of Physical Activities)
MET_PADRAO = 2.5
KCAL_MIN_POR_MET_KG = 0.0175  # 1 MET = 3,5 ml O2/kg/min ≈ 0,0175 kcal/kg/min


def altura_cotovelo_cm(perfil) -> float | None:
    if perfil is None:
        return None
    if perfil.altura_cotovelo_cm:
        return perfil.altura_cotovelo_cm
    return round(perfil.estatura_cm * ALTURA_COTOVELO_FRACAO, 1) if perfil.estatura_cm else None


def carga_referencia_kg(perfil) -> float:
    """Carga manual de referência por pessoa. Sempre o limite mais restritivo quando o perfil não permite mais."""
    if perfil is not None and perfil.sexo == "masculino" and perfil.faixa_etaria == "adulto":
        return CARGA_REF_ADULTO_MASCULINO_KG
    return CARGA_REF_RESTRITIVA_KG


def tolerancia_altura(tipo_passo: str, altura_trabalho_cm: float | None, perfil) -> dict | None:
    """Fadiga adicional quando a bancada está fora da faixa recomendada para a altura do cotovelo da equipe."""
    cotovelo = altura_cotovelo_cm(perfil)
    if cotovelo is None or not altura_trabalho_cm or tipo_passo not in FAIXA_ALTURA_CM:
        return None
    dif = altura_trabalho_cm - cotovelo
    baixo, alto = FAIXA_ALTURA_CM[tipo_passo]
    fora = baixo - dif if dif < baixo else (dif - alto if dif > alto else 0.0)
    if fora <= 0:
        return None
    pct = round(min(fora * TOLERANCIA_ALTURA_PCT_POR_CM, TOLERANCIA_ALTURA_MAX_PCT), 2)
    sentido = "alta" if dif > alto else "baixa"
    return {"categoria": "ergonomia: altura da bancada", "percentual": pct,
            "justificativa": f"Bancada de {altura_trabalho_cm:g} cm, {sentido} para o cotovelo da equipe ({cotovelo:g} cm): {fora:.1f} cm fora da faixa recomendada.",
            "fonte": "premissa do sistema (0,4 % por cm fora da faixa, máx. 8 %); calibrar com medições"}


def tolerancia_energia(tipo_passo: str, perfil) -> dict | None:
    """Descanso de Murrell, só quando o perfil traz peso corporal E o limite energético informado."""
    if perfil is None or not perfil.peso_corporal_kg or not perfil.limite_energetico_kcal_min:
        return None
    met = MET_REFERENCIA.get(tipo_passo, MET_PADRAO)
    w = met * perfil.peso_corporal_kg * KCAL_MIN_POR_MET_KG
    r = murrell_fracao_descanso(w, perfil.limite_energetico_kcal_min)
    if r <= 0:
        return None
    return {"categoria": "ergonomia: gasto de energia (Murrell)", "percentual": round(r / (1 + r) * 100, 2),
            "justificativa": f"Gasto estimado de {w:.1f} kcal/min ({met:g} MET × {perfil.peso_corporal_kg:g} kg) acima do limite informado de {perfil.limite_energetico_kcal_min:g} kcal/min.",
            "fonte": "Murrell: R=T(W−S)/(W−1,5); MET genérico, calibrar"}


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



def alerta_simples(a: str) -> tuple[str, str]:
    """(texto em linguagem comum, categoria). O texto técnico original segue em `detalhe`."""
    if "art. 198" in a:
        return "Segurança: uma peça acima de 60 kg não deve ser carregada por uma pessoa só. Use meio mecânico ou mais gente.", "seguranca"
    if "arts. 390" in a:
        return ("Segurança: a carga está acima do limite de referência para o perfil de quem executa. "
                "Confirme as regras aplicáveis com a área de segurança do trabalho."), "seguranca"
    if "NR-15" in a:
        return "Segurança: o ruído neste local está alto. Verifique a proteção auditiva e o tempo de exposição.", "seguranca"
    return a, "tecnico"
