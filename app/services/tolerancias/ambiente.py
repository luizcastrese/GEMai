"""Ambiente: ruído, temperatura, umidade e iluminância do local.

Só gera PERCENTUAL quando há norma verificada que o converta em tempo. Hoje não há: o texto oficial do IBUTG (NR-15, Anexo 3) NÃO foi
verificado nesta base e o IBUTG exige temperatura de globo e de bulbo úmido natural, que o local não registra; ruído (NR-15, Anexo 1)
limita a EXPOSIÇÃO, não define um acréscimo de tempo; para iluminância e umidade não há coeficiente com fonte. Logo: alertas, sem percentual.
"""
from .. import ergonomia
from .base import ContextoTolerancia, Saida, fonte

FONTE_RUIDO = "NR-15, Anexo 1"
FONTE_CALOR = "NR-15, Anexo 3 (IBUTG) / NHO-06 (Fundacentro)"


@fonte("ambiente")
def ambiente(ctx: ContextoTolerancia) -> Saida:
    s = Saida()
    vistos, com_dado = set(), False
    for e in ctx.locais:
        if e is None or e.id in vistos:
            continue
        vistos.add(e.id)
        if e.ruido_db and e.ruido_db > ergonomia.LIMITE_RUIDO_NR15_DBA:
            s.alertas.append({"msg": f"Ruído de {e.ruido_db:g} dB(A) em '{e.nome}' acima de {ergonomia.LIMITE_RUIDO_NR15_DBA:g} dB(A) (NR-15, 8 h): avaliar exposição.",
                              "categoria": "seguranca", "fonte": FONTE_RUIDO})
        if e.temperatura_c is not None and (e.temperatura_c > 30 or e.temperatura_c < 12):
            s.alertas.append({"msg": f"A temperatura em '{e.nome}' ({e.temperatura_c:g} °C) é extrema: avalie o conforto térmico (calor: IBUTG, NR-15 Anexo 3; "
                                     "frio: NR-36/NR-17). O sistema não converte isso em tolerância.", "categoria": "seguranca", "fonte": FONTE_CALOR})
        com_dado = com_dado or any(v is not None for v in (e.temperatura_c, e.umidade_pct, e.ruido_db, e.iluminancia_lux))
    if com_dado:
        s.premissas.append("Condições do ambiente (temperatura, umidade, ruído, iluminância) são registradas e geram alertas, mas não alteram o tempo: "
                           "não há norma verificada nesta base que as converta em percentual.")
    return s
