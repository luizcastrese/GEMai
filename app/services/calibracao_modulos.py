"""Calibração por MÓDULO: fator multiplicativo = mediana(tempo normal observado ÷ tempo normal previsto).

- amostra = uma operação concluída (ordem não cancelada) que tem módulo e previsão; o tempo observado é o dos apontamentos
  APROVADOS e não anulados de preparação + execução em TEMPO CORRIDO (a união dos intervalos: duas pessoas apontando o mesmo trabalho
  simultâneo contam uma vez), normalizado pelo ritmo médio de quem executou, ponderado pela duração (só na fração do tempo que
  depende do operador); a previsão é a do módulo em ritmo 100 e SEM fator
  de calibração (para não calibrar sobre a própria calibração);
- por (unidade, módulo): fator = mediana das razões, com ≥ `min_amostras_calibracao` amostras, limitado a 0,5–2,0;
- a prévia não grava; registrar cria uma proposta PENDENTE; só uma pessoa a valida (validado + vigente) e só a validada
  entra no cálculo, rotulada `calibrado` com o nº de amostras;
- é um fator do MÓDULO, nunca de uma pessoa (o ritmo individual só normaliza o observado).

Família (produto × módulo): pedidos do mesmo produto com dimensões diferentes têm o MESMO núcleo de cálculo, mas o erro do
módulo pode crescer (ou encolher) com o tamanho. Por isso, além do fator geral, cada produto com amostras suficientes
ganha um fator que ESCALA com o porte do pedido, aprendido dos pedidos já feitos (os maiores informam os menores):
- porte = tempo normal previsto POR UNIDADE do pedido (já deriva das medidas pelas fórmulas das peças; nada extra a informar);
- ajuste robusto (Theil–Sen) de ln(razão) contra ln(porte): expoente `b` e fator no porte de referência (mediana dos portes);
  fator(porte) = fator_ref × (porte ÷ porte_ref)^b, limitado a 0,5–2,0; b limitado a −0,5…1,0;
- exige ≥ `min_amostras_familia` amostras, ≥ 3 tamanhos distintos e dispersão de porte ≥ 1,25×; senão não há como aprender a
  escala e vale o fator geral do módulo;
- a escala só é proposta se, numa prova com dados reservados (leave-one-out), reduzir o erro em ≥ 10 % frente a um fator constante
  da família; senão fica o fator constante (e a proposta diz isso);
- fora do intervalo observado (±50 %) o porte é travado na borda e o resultado é rotulado "extrapolado";
- precedência no cálculo: família validada do produto > fator geral validado do módulo > nada (coeficientes genéricos).

Robustez e pequenas amostras (pensado para pequenos negócios, que demoram a juntar pedidos):
- **identificador de Hampel**: antes da mediana, sai a razão cujo ln se afasta da mediana dos ln por mais de 3 × 1,4826 × MAD
  (desvio absoluto mediano). Pega ordem esquecida aberta ou apontamento trocado sem limite arbitrário; o nº descartado é declarado;
- **credibilidade de flutuação limitada**: com n entre `min_amostras_preliminar` e o mínimo, a proposta é PRELIMINAR e o fator é
  1 + Z·(mediana − 1), com Z = √(n ÷ n_completo) e n_completo = `min_amostras_calibracao`. Em n = n_completo, Z = 1 e o resultado
  é o fator pleno de antes. A proposta preliminar também só vale depois de validada por uma pessoa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Apontamento, CalibracaoModulo, Ordem, OrdemOperacao
from . import ritmo, timecalc
from .modulos import catalogo

FATOR_MIN, FATOR_MAX = 0.5, 2.0
EXPOENTE_MIN, EXPOENTE_MAX = -0.5, 1.0
MIN_TAMANHOS = 3        # tamanhos distintos (portes que diferem > 5 %) para enxergar uma escala
MIN_DISPERSAO = 1.25    # maior porte ÷ menor porte
FOLGA_EXTRAPOLACAO = 1.5  # além do intervalo observado ×1,5 o porte é travado na borda
HAMPEL_K = 3.0  # nº de desvios robustos (1,4826 × MAD ≈ desvio-padrão sob normalidade) para considerar uma razão discrepante


@dataclass
class Sugestao:
    unidade_id: int
    modulo: str
    amostras: int
    minimo: int
    mediana_bruta: float | None
    fator: float | None
    limitado: bool
    status: str  # sugerido | insuficiente
    produto_id: int | None = None  # None = geral do módulo; com produto = família (escala com o porte)
    expoente: float = 0.0
    porte_ref: float | None = None
    porte_min: float | None = None
    porte_max: float | None = None
    # Prova com dados reservados (leave-one-out): erro típico (%) sem calibração, com um fator constante e com o modelo proposto.
    erro_sem_pct: float | None = None
    erro_constante_pct: float | None = None
    erro_com_pct: float | None = None
    nota: str = ""
    descartadas: int = 0  # razões discrepantes retiradas pelo identificador de Hampel
    credibilidade: float = 1.0  # Z aplicado ao desvio do fator (1 = pleno)
    total_do_pedido: int = 0  # amostras vindas de apontamento no total do pedido (distribuído pelo previsto)


@dataclass
class Amostra:
    unidade_id: int
    modulo: str
    produto_id: int | None
    porte: float | None  # tempo normal previsto por unidade do pedido
    razao: float  # tempo normal observado ÷ previsto
    total: bool = False  # veio do apontamento no total do pedido: informa o nível geral, não o módulo isolado


def hampel(razoes: list[float], k: float = HAMPEL_K) -> tuple[list[int], int]:
    """(índices mantidos, nº descartado). Sobre ln(razão); com menos de 4 amostras ou MAD = 0 não descarta nada."""
    idx = [i for i, r in enumerate(razoes) if r and r > 0]
    if len(idx) < 4:
        return idx, len(razoes) - len(idx)
    ls = {i: math.log(razoes[i]) for i in idx}
    med = timecalc.mediana(list(ls.values()))
    mad = timecalc.mediana([abs(v - med) for v in ls.values()])
    if mad <= 0:
        return idx, len(razoes) - len(idx)
    lim = k * 1.4826 * mad
    mantidos = [i for i in idx if abs(ls[i] - med) <= lim]
    return mantidos, len(razoes) - len(mantidos)


def credibilidade(n: int, n_completo: int) -> float:
    """Credibilidade de flutuação limitada: Z = √(n ÷ n_completo), limitada a 1."""
    return 1.0 if n_completo <= 0 else min(1.0, math.sqrt(max(n, 0) / n_completo))


def amostras(db: Session, empresa_id: int, unidade_ids: list[int]) -> list[Amostra]:
    """Uma amostra por operação concluída com módulo e previsão: razão (observado normal ÷ previsto) e o porte do pedido."""
    if not unidade_ids:
        return []
    rows = db.execute(
        select(OrdemOperacao, Ordem.unidade_id, Ordem.produto_id, Ordem.quantidade).join(Ordem, Ordem.id == OrdemOperacao.ordem_id).where(
            OrdemOperacao.empresa_id == empresa_id, OrdemOperacao.status == "concluida", OrdemOperacao.modulo.is_not(None),
            OrdemOperacao.previsto_normal_min > 0, Ordem.status != "cancelada", Ordem.unidade_id.in_(unidade_ids))).all()
    if not rows:
        return []
    por_oo = {oo.id: (oo, uid, pid, qtd) for oo, uid, pid, qtd in rows}
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_operacao_id.in_(por_oo), Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    ritmos = ritmo.ritmos_das_pessoas(db, empresa_id, {a.pessoa_id for a in apts if a.pessoa_id})
    # Tempo CORRIDO: pessoas trabalhando juntas contam uma vez (união dos intervalos), não uma por pessoa. O ritmo entra como a média
    # ponderada pela duração de cada apontamento, aplicada só na fração que depende do operador. Com uma pessoa só, dá o mesmo
    # resultado de antes (duração · (f·ritmo + 1 − f)); com equipe, o previsto (corrido) e o observado passam a ser comparáveis.
    grupos: dict[int, list[Apontamento]] = {}
    for a in apts:
        grupos.setdefault(a.ordem_operacao_id, []).append(a)
    observado: dict[int, float] = {}
    for oo_id, lista in grupos.items():
        oo = por_oo[oo_id][0]
        f = oo.fracao_operador if oo.fracao_operador is not None else 1.0
        corrido = timecalc.uniao_minutos((a.inicio, a.fim) for a in lista)
        pesos = [(timecalc.duracao_min(a.inicio, a.fim) or 0.0, ritmos.get(a.pessoa_id)) for a in lista]
        total = sum(d for d, _ in pesos)
        if total <= 0:
            continue
        rit = sum(d * (r.valor / 100.0 if r is not None and r.conhecido else 1.0) for d, r in pesos) / total
        observado[oo_id] = corrido * (f * rit + (1.0 - f))
    totais = {oo_id for oo_id, lista in grupos.items() if any((a.dados_extras or {}).get("origem") == "total_do_pedido" for a in lista)}
    out: list[Amostra] = []
    for oo_id, obs in observado.items():
        if obs <= 0:
            continue
        oo, uid, pid, qtd = por_oo[oo_id]
        porte = oo.previsto_normal_min / qtd if qtd and qtd > 0 else None
        out.append(Amostra(uid, oo.modulo, pid, porte, obs / oo.previsto_normal_min, total=oo_id in totais))
    return out


def razoes(db: Session, empresa_id: int, unidade_ids: list[int]) -> dict[tuple[int, str], list[float]]:
    """{(unidade_id, módulo): [observado normal ÷ previsto, …]} das operações concluídas com módulo e previsão (todos os produtos)."""
    out: dict[tuple[int, str], list[float]] = {}
    for a in amostras(db, empresa_id, unidade_ids):
        out.setdefault((a.unidade_id, a.modulo), []).append(a.razao)
    return out


@dataclass
class Familia:
    fator: float  # no porte de referência, já limitado
    bruto: float
    limitado: bool
    expoente: float
    porte_ref: float
    porte_min: float
    porte_max: float


def ajustar_familia(pares: list[tuple[float, float]]) -> Familia | None:
    """pares = [(porte, razão)]. None quando não há como aprender a escala (poucos tamanhos ou pouca dispersão)."""
    pares = [(x, r) for x, r in pares if x and x > 0 and r and r > 0]
    if len(pares) < 2:
        return None
    lx = [math.log(x) for x, _ in pares]
    lr = [math.log(r) for _, r in pares]
    if len({round(v / 0.05) for v in lx}) < MIN_TAMANHOS or max(lx) - min(lx) < math.log(MIN_DISPERSAO):
        return None
    inclinacoes = [(lr[j] - lr[i]) / (lx[j] - lx[i]) for i in range(len(pares)) for j in range(i + 1, len(pares))
                   if abs(lx[j] - lx[i]) >= 0.05]
    if not inclinacoes:
        return None
    b = min(max(timecalc.mediana(inclinacoes), EXPOENTE_MIN), EXPOENTE_MAX)
    if abs(b) * (max(lx) - min(lx)) < 0.05:  # a escala quase não muda o fator na faixa observada: vale uma constante
        b = 0.0
    ref = timecalc.mediana([x for x, _ in pares])
    bruto = math.exp(timecalc.mediana([lr[i] - b * (lx[i] - math.log(ref)) for i in range(len(pares))]))
    fator = min(max(bruto, FATOR_MIN), FATOR_MAX)
    return Familia(round(fator, 4), round(bruto, 4), fator != bruto, round(b, 4), round(ref, 4),
                   round(min(x for x, _ in pares), 4), round(max(x for x, _ in pares), 4))


def _pct(erros_ln: list[float]) -> float | None:
    """Erro típico em %: média do |ln(previsto ÷ observado)| convertida (0,18 → 20 %)."""
    return round((math.exp(sum(erros_ln) / len(erros_ln)) - 1) * 100, 1) if erros_ln else None


def _limitar_ln(v: float) -> float:
    return math.log(min(max(math.exp(v), FATOR_MIN), FATOR_MAX))


def erro_sem_calibracao(rs: list[float]) -> float | None:
    return _pct([abs(math.log(r)) for r in rs if r > 0])


def erro_constante_loo(rs: list[float]) -> float | None:
    """Prova com dados reservados: cada pedido é previsto pelo fator (mediana) dos OUTROS pedidos."""
    ls = [math.log(r) for r in rs if r > 0]
    if len(ls) < 3:
        return None
    return _pct([abs(l - _limitar_ln(timecalc.mediana(ls[:i] + ls[i + 1:]))) for i, l in enumerate(ls)])


def erro_escala_loo(pares: list[tuple[float, float]]) -> float | None:
    """Idem, com o modelo que escala com o porte (refeito sem o pedido testado; sem escala aprendível, usa o fator constante)."""
    pares = [(x, r) for x, r in pares if x and x > 0 and r and r > 0]
    if len(pares) < 3:
        return None
    erros = []
    for i, (x, r) in enumerate(pares):
        resto = pares[:i] + pares[i + 1:]
        fam = ajustar_familia(resto)
        if fam is None or not fam.expoente:
            pred = _limitar_ln(timecalc.mediana([math.log(q) for _, q in resto]))
        else:
            pred = _limitar_ln(math.log(fam.fator) + fam.expoente * (math.log(x) - math.log(fam.porte_ref)))
        erros.append(abs(math.log(r) - pred))
    return _pct(erros)


# a escala só é proposta se reduzir o erro nos dados reservados em pelo menos 10 % em relação ao fator constante
GANHO_MINIMO_ESCALA = 0.9


def previa(db: Session, empresa_id: int, unidade_ids: list[int]) -> list[Sugestao]:
    """Sugestões gerais (por módulo) e por família (produto × módulo). Não grava."""
    cfg = get_settings()
    minimo, min_fam = max(cfg.min_amostras_calibracao, 1), max(cfg.min_amostras_familia, 2)
    min_prel = min(max(cfg.min_amostras_preliminar, 1), minimo)
    validos = catalogo.da_empresa(db, empresa_id)
    todas = [a for a in amostras(db, empresa_id, unidade_ids) if a.modulo in validos]
    gerais: dict[tuple[int, str], list[Amostra]] = {}
    familias: dict[tuple[int, str, int], list[Amostra]] = {}
    for a in todas:
        gerais.setdefault((a.unidade_id, a.modulo), []).append(a)
        if a.produto_id is not None:
            familias.setdefault((a.unidade_id, a.modulo, a.produto_id), []).append(a)
    sugestoes = []
    for (uid, modulo), am in sorted(gerais.items()):
        brutas = [a.razao for a in am]
        mantidos, descartadas = hampel(brutas)
        xs = [brutas[i] for i in mantidos]
        n_total = sum(1 for i in mantidos if am[i].total)
        if len(xs) < min_prel:
            sugestoes.append(Sugestao(uid, modulo, len(xs), minimo, None, None, False, "insuficiente", descartadas=descartadas))
            continue
        z = credibilidade(len(xs), minimo)
        mediana = timecalc.mediana(xs)
        bruta = 1.0 + z * (mediana - 1.0)
        fator = min(max(bruta, FATOR_MIN), FATOR_MAX)
        sem, com = erro_sem_calibracao(xs), erro_constante_loo(xs)
        notas = []
        if sem is not None and com is not None and com > sem:
            notas.append("Nos dados reservados este fator NÃO melhora o erro típico: o desvio parece depender do tamanho do pedido, não de um "
                         "nível geral. Prefira a calibração por produto (que escala com o porte), se houver.")
        if z < 1.0:
            notas.append(f"Proposta PRELIMINAR com {len(xs)} de {minimo} pedidos: ajuste parcial (credibilidade Z = {z:.2f}; "
                         f"a mediana observada é × {mediana:.2f}).")
        if descartadas:
            notas.append(f"{descartadas} registro(s) muito fora do padrão foram desconsiderados (identificador de Hampel).")
        if not (n_total and n_total * 2 >= len(xs)) and len(xs) >= 3:
            from . import ciclo  # leitura padrão × fluxo (import local: ciclo usa este módulo)
            leitura = ciclo.classificar(xs, n_total)
            if leitura["leitura"] == "corrigir_fluxo":
                notas.append("Atenção: o desvio varia muito de pedido a pedido; parece ser o FLUXO, não o padrão. Antes de aplicar, veja "
                             "«O que o real mostrou» no plano: calibrar agora esconderia o problema.")
        if n_total and n_total * 2 >= len(xs):
            notas.append("A maior parte dos registros foi apontada no total do pedido: o fator mostra o nível geral, não esta atividade isolada.")
        sugestoes.append(Sugestao(uid, modulo, len(xs), minimo, round(bruta, 4), round(fator, 4), fator != bruta,
                                  "sugerido" if z >= 1.0 else "preliminar", erro_sem_pct=sem, erro_com_pct=com, nota=" ".join(notas),
                                  descartadas=descartadas, credibilidade=round(z, 4), total_do_pedido=n_total))
    for (uid, modulo, pid), am in sorted(familias.items()):
        mantidos, _desc = hampel([a.razao for a in am])
        am = [am[i] for i in mantidos]
        pares = [(a.porte, a.razao) for a in am if a.porte]
        fam = ajustar_familia(pares) if len(am) >= min_fam else None
        if fam is None:
            sugestoes.append(Sugestao(uid, modulo, len(am), min_fam, None, None, False, "insuficiente", produto_id=pid))
            continue
        rs = [r for _, r in pares]
        sem, const = erro_sem_calibracao(rs), erro_constante_loo(rs)
        esc, nota = erro_escala_loo(pares), ""
        if fam.expoente and (esc is None or const is None or esc > const * GANHO_MINIMO_ESCALA):
            # a escala não provou ganho nos dados reservados: fica o fator constante da família (mais simples, menos risco)
            nota = (f"Escala com o porte descartada: erro típico {esc:g} % contra {const:g} % com fator constante." if esc is not None and const is not None
                    else "Escala com o porte descartada: poucos dados para prová-la.")
            bruto = timecalc.mediana(rs)
            fator = min(max(bruto, FATOR_MIN), FATOR_MAX)
            fam = Familia(round(fator, 4), round(bruto, 4), fator != bruto, 0.0, fam.porte_ref, fam.porte_min, fam.porte_max)
            esc = None
        sugestoes.append(Sugestao(uid, modulo, len(am), min_fam, fam.bruto, fam.fator, fam.limitado, "sugerido", produto_id=pid,
                                  expoente=fam.expoente, porte_ref=fam.porte_ref, porte_min=fam.porte_min, porte_max=fam.porte_max,
                                  erro_sem_pct=sem, erro_constante_pct=const, erro_com_pct=esc if esc is not None else const, nota=nota))
    return sugestoes


def vigente_exato(db: Session, empresa_id: int, unidade_id: int | None, modulo: str, produto_id: int | None = None) -> CalibracaoModulo | None:
    """Calibração VALIDADA e vigente exatamente desta chave (produto_id None = fator geral do módulo)."""
    if unidade_id is None:
        return None
    return db.scalar(select(CalibracaoModulo).where(
        CalibracaoModulo.empresa_id == empresa_id, CalibracaoModulo.unidade_id == unidade_id, CalibracaoModulo.modulo == modulo,
        CalibracaoModulo.produto_id.is_(None) if produto_id is None else CalibracaoModulo.produto_id == produto_id,
        CalibracaoModulo.vigente.is_(True), CalibracaoModulo.status == "validado"))


def fator_vigente(db: Session, empresa_id: int, unidade_id: int | None, modulo: str, produto_id: int | None = None) -> CalibracaoModulo | None:
    """Calibração a usar: a da FAMÍLIA (produto) se validada; senão o fator geral do módulo; senão None (fator 1, coeficientes genéricos)."""
    if produto_id is not None:
        fam = vigente_exato(db, empresa_id, unidade_id, modulo, produto_id)
        if fam is not None:
            return fam
    return vigente_exato(db, empresa_id, unidade_id, modulo)


def fator_para(c: CalibracaoModulo, porte: float | None) -> tuple[float, bool]:
    """(fator efetivo, extrapolou?) para o porte do pedido. Geral ou família sem escala: o fator fixo."""
    if c.produto_id is None or not c.expoente or porte is None or porte <= 0 or not c.porte_ref or not c.porte_min or not c.porte_max:
        return c.fator, False
    x = min(max(porte, c.porte_min / FOLGA_EXTRAPOLACAO), c.porte_max * FOLGA_EXTRAPOLACAO)
    k = c.fator * (x / c.porte_ref) ** c.expoente
    return min(max(k, FATOR_MIN), FATOR_MAX), (porte < c.porte_min or porte > c.porte_max)


def como_dict(c: CalibracaoModulo | None, porte: float | None = None) -> dict | None:
    if c is None:
        return None
    k, extra = fator_para(c, porte)
    d = {"fator": k, "amostras": c.amostras, "versao": c.versao}
    if c.produto_id is not None:
        d["fonte"] = (f"Calibração validada da família: {c.amostras} amostras aprovadas deste produto"
                      + (f", escala com o porte (expoente {c.expoente:g})" if c.expoente else "") + f" (v{c.versao})"
                      + ("; porte fora do já observado: fator travado na borda (extrapolado)" if extra else ""))
        d["extrapolado"] = extra
    return d
