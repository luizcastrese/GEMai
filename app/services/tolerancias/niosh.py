"""Carga: equação revisada do NIOSH (Waters et al., 1993). O LI é calculado pelo método; a conversão LI → % de fadiga é PREMISSA do
sistema (não há tabela normativa para ela), por isso vai rotulada."""
from .. import ergonomia
from .base import ContextoTolerancia, Saida, Tolerancia, fonte

FONTE = "NIOSH Revised Lifting Equation (Waters et al., 1993; NIOSH Pub. 94-110)"
PREMISSA = "A conversão do Índice de Levantamento (LI) em % de tolerância é premissa do sistema, não valor normativo; calibrar com medições."


@fonte("niosh")
def niosh(ctx: ContextoTolerancia) -> Saida:
    s = Saida()
    if not ctx.levantamento:
        return s
    n = ergonomia.niosh(ctx.levantamento, ctx.carga_kg)
    if not n.get("completo"):
        s.pendencias.append("Dados de levantamento (NIOSH) incompletos: " + "; ".join(n["faltantes"]))
        return s
    p = ergonomia.tolerancia_por_li(n["li"], n["li_infinito"])
    li = "∞" if n["li_infinito"] else n["li"]
    if p > 0:
        s.itens.append(Tolerancia("fadiga por carga (LI)", round(p * 100, 2), FONTE, PREMISSA, f"LI = {li}: acima do recomendado pelo NIOSH."))
        s.premissas.append(PREMISSA)
    if n["li_infinito"] or n["li"] > 1:
        s.alertas.append({"msg": f"Índice de levantamento {li} > 1: reprojetar (ajuda mecânica, dividir carga, aproximar da altura de pega) e avaliar via AET.",
                          "categoria": "seguranca", "fonte": FONTE})
    return s
