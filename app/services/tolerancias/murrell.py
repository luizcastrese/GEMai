"""Descanso por gasto energético: R/T = (W − S)/(W − 1,5) (Murrell). O limite S NÃO tem valor embutido (as fontes divergem):
vem do perfil; sem ele, pendência."""
from .. import ergonomia
from .base import ContextoTolerancia, Saida, Tolerancia, fonte

FONTE = "Murrell: R = T·(W − S)/(W − 1,5), com W = gasto no trabalho e S = limite adotado (kcal/min)"


@fonte("murrell")
def murrell(ctx: ContextoTolerancia) -> Saida:
    s = Saida()
    w = ctx.gasto_energetico_kcal_min
    if not w:
        return s
    lim = getattr(ctx.perfil, "limite_energetico_kcal_min", None) if ctx.perfil is not None else None
    if not lim:
        s.pendencias.append("Gasto energético informado, mas falta o limite energético (S) do perfil de mão de obra: não há valor padrão porque as fontes divergem.")
        return s
    r = ergonomia.murrell_fracao_descanso(w, lim)
    if r > 0:
        s.itens.append(Tolerancia("descanso por gasto energético (Murrell)", round(r / (1 + r) * 100, 2), FONTE,
                                  justificativa=f"W={w:g} kcal/min acima do limite adotado S={lim:g}."))
    return s
