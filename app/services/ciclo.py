"""Ciclo padrão ↔ fluxo: o que fazer quando o real se afasta do tempo padrão.

O tempo padrão é a META do método. Quando o real se afasta dele, há duas leituras, e a Engenharia de Produção trata as duas:
1. **o padrão estava errado** (o método foi seguido e o previsto era otimista ou pessimista) → corrigir o PADRÃO (calibração);
2. **o processo se desviou do método** (transporte a mais, espera, gargalo, preparo repetido…) → corrigir o FLUXO (estudo de métodos)
   e manter o padrão como meta.

Critério (controle estatístico de processo, Shewhart): variação de causa COMUM é estável de pedido a pedido; variação de causa
ESPECIAL é irregular. Por atividade, sobre r = realizado ÷ previsto (tempo normal) dos pedidos medidos:
- desvio típico d = mediana de ln r; variabilidade s = 1,4826 × MAD de ln r (desvio-padrão robusto);
- |d| ≤ ln 1,10 → **no padrão**; s ≤ 0,15 e |d| > ln 1,10 → **corrigir o padrão** (desvio sistemático e estável);
  s > 0,15 e d > ln 1,10 → **corrigir o fluxo** (desvio irregular: causas especiais); s > 0,15 e d < −ln 1,10 → o padrão é folgado
  mas instável: **medir mais** antes de mexer;
- poucos pedidos (< 3) → **medir mais**; maioria medida no total do pedido → **nível geral** (não separa as atividades).
Os limiares (±10 % e 0,15) são ESCOLHAS DO PROJETO, declaradas; não são da norma.

No pedido medido passo a passo, o desvio também é localizado: a etapa que responde por ≥ 60 % do excesso é a **etapa crítica**.
As sugestões de ajuste do fluxo seguem o ECRS do estudo de métodos (eliminar, combinar, reorganizar, simplificar; Barnes) por tipo de
etapa; as que mexem em equipe, lotes ou meio de movimentação são **recalculadas pelo motor** (arranjo), as demais são para verificar
no local e, depois de aplicadas, medidas de novo.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Apontamento, Ordem, PlanoTrabalho
from . import calibracao_modulos, timecalc

LIMIAR_DESVIO = math.log(1.10)
LIMIAR_DISPERSAO = 0.15
MIN_PEDIDOS = 3
CONCENTRACAO = 0.6

ARQUETIPO_EMBUTIDO = {"movimentacao": "deslocamento", "corte": "processamento_meio", "bordo": "processamento_meio",
                      "furacao": "processamento_meio", "montagem": "manual", "conferencia": "inspecao"}

ECRS = {
    "deslocamento": [("Eliminar", "Levar direto ao destino, sem paradas ou depósitos intermediários."),
                     ("Reorganizar", "Aproximar os locais de origem e destino (menos metros por viagem)."),
                     ("Simplificar", "Levar mais itens por viagem com um carrinho ou outro meio de movimentação.")],
    "processamento_meio": [("Combinar", "Juntar pedidos parecidos para preparar a máquina uma vez só."),
                           ("Reorganizar", "Separar o preparo: deixar material, ferramenta e medidas prontos antes de ligar a máquina."),
                           ("Simplificar", "Conferir na ficha técnica se a velocidade usada é a real da máquina e do material.")],
    "manual": [("Combinar", "Dividir o trabalho manual entre mais pessoas (balanceamento)."),
               ("Reorganizar", "Deixar itens e ferramentas ao alcance, na ordem em que são usados."),
               ("Simplificar", "Usar um gabarito ou dispositivo para posicionar e fixar sem medir de novo.")],
    "espera": [("Reorganizar", "Adiantar outra etapa enquanto espera (secagem, cura), em vez de ficar parado.")],
    "inspecao": [("Combinar", "Conferir durante a montagem, em vez de só no fim."),
                 ("Eliminar", "Evitar conferência repetida do mesmo item.")],
}


def _real(apts: list) -> float:
    return timecalc.uniao_minutos((a.inicio, a.fim) for a in apts if a.fim)


def diagnostico_pedido(db: Session, empresa_id: int, o: Ordem) -> dict | None:
    """Onde o real se afastou do previsto neste pedido (tempo padrão da ordem × tempo corrido aprovado)."""
    if o is None or o.status != "concluida":
        return None
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_id == o.id, Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    if not apts:
        return {"medido": False}
    total = any((a.dados_extras or {}).get("origem") == "total_do_pedido" for a in apts)
    real = _real(apts)
    previsto = o.tempo_estimado_min or 0.0
    etapas = []
    for x in o.operacoes:
        mine = [a for a in apts if a.ordem_operacao_id == x.id]
        prev = (x.tempo_prep_est_min or 0.0) + (x.tempo_exec_est_min or 0.0)
        r = _real(mine)
        prep = _real([a for a in mine if a.tipo == "preparacao"])
        etapas.append({"etapa": x.nome, "modulo": x.modulo, "previsto_min": round(prev, 2), "realizado_min": round(r, 2),
                       "preparo_realizado_min": round(prep, 2), "excesso_min": round(r - prev, 2),
                       "desvio_pct": round((r / prev - 1) * 100, 1) if prev > 0 and r > 0 else None})
    out = {"medido": True, "forma": "total" if total else "passo_a_passo", "previsto_min": round(previsto, 2), "realizado_min": round(real, 2),
           "desvio_pct": round((real / previsto - 1) * 100, 1) if previsto else None, "etapas": etapas, "etapa_critica": None}
    if not total:
        excesso = sum(e["excesso_min"] for e in etapas if e["excesso_min"] > 0)
        pior = max(etapas, key=lambda e: e["excesso_min"], default=None)
        if pior and excesso > 0 and len(etapas) > 1 and pior["excesso_min"] / excesso >= CONCENTRACAO:
            out["etapa_critica"] = {**pior, "parcela_do_excesso_pct": round(pior["excesso_min"] / excesso * 100, 1)}
    return out


def classificar(razoes: list[float], totais: int) -> dict:
    """Leitura de uma atividade a partir das razões realizado ÷ previsto dos pedidos medidos."""
    mantidos, descartadas = calibracao_modulos.hampel(razoes)
    rs = [razoes[i] for i in mantidos]
    n = len(rs)
    base = {"pedidos": n, "descartados": descartadas, "desvio_tipico_pct": None, "variabilidade": None}
    if n < MIN_PEDIDOS:
        return {**base, "leitura": "medir_mais", "texto": f"Poucos pedidos medidos ({n} de {MIN_PEDIDOS}): ainda não dá para separar padrão de fluxo."}
    ls = [math.log(r) for r in rs]
    d = timecalc.mediana(ls)
    s = 1.4826 * timecalc.mediana([abs(v - d) for v in ls])
    base.update(desvio_tipico_pct=round((math.exp(d) - 1) * 100, 1), variabilidade=round(s, 3))
    if totais * 2 >= n:
        return {**base, "leitura": "nivel_geral",
                "texto": "A maior parte dos pedidos foi medida no total: isso mostra o nível geral, não onde está a diferença. "
                         "Meça alguns pedidos passo a passo para saber se é o padrão ou o fluxo."}
    if abs(d) <= LIMIAR_DESVIO:
        return {**base, "leitura": "no_padrao", "texto": "O real está dentro de ±10 % do padrão: nada a corrigir."}
    if s <= LIMIAR_DISPERSAO:
        return {**base, "leitura": "corrigir_padrao",
                "texto": f"O desvio é estável de pedido a pedido ({base['desvio_tipico_pct']:+g} %): o padrão está {'otimista' if d > 0 else 'folgado'}. "
                         "Ajuste o tempo (calibração)."}
    if d > 0:
        return {**base, "leitura": "corrigir_fluxo",
                "texto": f"Leva {base['desvio_tipico_pct']:+g} % e varia muito de um pedido para outro: o problema é o fluxo, não o padrão. "
                         "Ajuste o jeito de fazer e meça de novo; calibrar agora esconderia o problema."}
    return {**base, "leitura": "medir_mais", "texto": "O real fica abaixo do padrão, mas varia muito: meça mais pedidos antes de mudar o tempo."}


def atividades_do_plano(db: Session, empresa_id: int, plano: PlanoTrabalho) -> list[dict]:
    """Leitura de cada atividade do plano com o histórico de pedidos medidos na unidade."""
    from . import decomposicao
    amostras = calibracao_modulos.amostras(db, empresa_id, [plano.unidade_id])
    modulos = list(dict.fromkeys(p.modulo for p in plano.passos if p.modulo))
    titulo = {p.modulo: p.nome for p in plano.passos}
    colunas = decomposicao.da_unidade(db, empresa_id, plano.unidade_id)
    out = []
    for m in modulos:
        am = [a for a in amostras if a.modulo == m]
        c = classificar([a.razao for a in am], sum(1 for a in am if a.total))
        partes = {col.parte: col for col in colunas if col.modulo == m}
        dec = {parte: {"fator": col.fator, "identificavel": col.identificavel, "peso_dos_dados": col.peso_dos_dados}
               for parte, col in partes.items()}
        k = decomposicao.fator_da_atividade(colunas, m)
        if c["leitura"] == "nivel_geral" and k is not None:
            # medido no total, mas a decomposição entre pedidos de composições diferentes separa esta atividade
            onde = max(partes.values(), key=lambda col: abs(math.log(col.fator)) if col.identificavel else -1)
            nome = {"preparo": "no preparo", "execucao": "na execução"}[onde.parte]
            if abs(math.log(k)) <= LIMIAR_DESVIO:
                c = {**c, "leitura": "no_padrao", "texto": "Pela decomposição entre pedidos, esta atividade está dentro de ±10 % do padrão."}
            else:
                c = {**c, "leitura": "corrigir_padrao", "desvio_tipico_pct": round((k - 1) * 100, 1),
                     "texto": f"Pela decomposição entre pedidos de composições diferentes, a diferença está {nome} (× {onde.fator:.2f}). "
                              "Ajuste o tempo (calibração)."}
        out.append({"modulo": m, "etapa": titulo.get(m, m), **c, "decomposicao": dec})
    return out


def decisao(pedido: dict | None, atividades: list[dict]) -> dict:
    """Uma frase para o dono: corrigir o fluxo, corrigir o padrão, nada a fazer ou medir mais."""
    fluxo = [a for a in atividades if a["leitura"] == "corrigir_fluxo"]
    padrao = [a for a in atividades if a["leitura"] == "corrigir_padrao"]
    critica = (pedido or {}).get("etapa_critica")
    if critica:
        return {"acao": "corrigir_fluxo", "foco": [critica["modulo"]],
                "texto": f"Neste pedido, «{critica['etapa']}» respondeu por {critica['parcela_do_excesso_pct']:g} % do tempo a mais. "
                         "Veja como ajustar essa etapa."}
    if fluxo:
        return {"acao": "corrigir_fluxo", "foco": [a["modulo"] for a in fluxo],
                "texto": "Há etapas com desvio irregular: " + ", ".join(f"«{a['etapa']}»" for a in fluxo) + ". O ajuste é no fluxo."}
    if padrao:
        return {"acao": "corrigir_padrao", "foco": [a["modulo"] for a in padrao],
                "texto": "O desvio é estável em " + ", ".join(f"«{a['etapa']}»" for a in padrao) + ": ajuste o tempo em «Ajustar meus tempos»."}
    if atividades and all(a["leitura"] == "no_padrao" for a in atividades):
        return {"acao": "manter", "foco": [], "texto": "O real está seguindo o padrão. Continue medindo."}
    if any(a["leitura"] == "nivel_geral" for a in atividades):
        return {"acao": "medir_passo_a_passo", "foco": [],
                "texto": "Os pedidos foram medidos no total. Meça alguns passo a passo para descobrir onde está a diferença."}
    return {"acao": "medir_mais", "foco": [], "texto": "Meça mais pedidos: com 3 ou mais já dá para saber se é o padrão ou o fluxo."}


def sugestoes_ecrs(plano: PlanoTrabalho, foco: list[str], catalogo: dict) -> list[dict]:
    """Ajustes de método (ECRS) por tipo de etapa em foco; para verificar no local e medir de novo."""
    out, vistos = [], set()
    alvo = [p for p in plano.passos if p.modulo in foco] or list(plano.passos)
    for p in alvo:
        mod = catalogo.get(p.modulo)
        arq = (mod.arquetipo if mod is not None and mod.arquetipo else None) or ARQUETIPO_EMBUTIDO.get(p.modulo, "manual")
        for principio, texto in ECRS.get(arq, []):
            if (arq, principio) in vistos:
                continue
            vistos.add((arq, principio))
            out.append({"etapa": p.nome, "principio": principio, "texto": texto, "recalculado": False})
    return out


def alternativas_recalculadas(ctx, plano: PlanoTrabalho, produto) -> list[dict]:
    """Equipe, lotes e meio de movimentação: recalculados pelo motor (arranjo) e comparados ao plano atual."""
    from .arranjo import servico as arranjo
    cfg = {k: v for k, v in (plano.config or {}).items() if k in ("inicio", "blocos", "so_dias_uteis", "perfil_id", "incluir_conferencia")}
    from datetime import datetime
    if isinstance(cfg.get("inicio"), str):
        cfg["inicio"] = datetime.fromisoformat(cfg["inicio"])
    cfg.update(especificacoes=plano.especificacoes or {}, estrutura=plano.estrutura)
    r = arranjo.recomendar(ctx, produto, plano.quantidade, plano.unidade_id, cfg, pessoas_max=4, n_melhores=4)
    atual = (plano.totais or {}).get("pessoas") or (plano.config or {}).get("pessoas") or 1
    out = []
    for c in r["candidatos"]:
        if c["pessoas"] == atual and c["lotes"] == 1 and not c.get("meio_id"):
            principio = "Atual"
        elif c["lotes"] > 1:
            principio = "Reorganizar"
        elif c.get("meio_id"):
            principio = "Simplificar"
        else:
            principio = "Combinar"
        out.append({"principio": principio, "rotulo": c["rotulo"], "prazo_min": c["makespan_min"], "pessoas_hora": c["pessoas_hora"],
                    "gargalo": c["gargalo"], "escolha": {k: c[k] for k in ("pessoas", "lotes", "regra", "meio_id")}, "recalculado": True})
    return out


def ciclo_do_plano(ctx, plano: PlanoTrabalho, produto, *, alternativas: bool = False) -> dict:
    from .modulos import catalogo
    ordem = ctx.db.get(Ordem, plano.ordem_id) if plano.ordem_id else None
    pedido = diagnostico_pedido(ctx.db, ctx.empresa_id, ordem) if ordem is not None and ordem.empresa_id == ctx.empresa_id else None
    atividades = atividades_do_plano(ctx.db, ctx.empresa_id, plano)
    d = decisao(pedido, atividades)
    sugestoes = sugestoes_ecrs(plano, d["foco"], catalogo.da_empresa(ctx.db, ctx.empresa_id)) if d["acao"] == "corrigir_fluxo" else []
    alt = alternativas_recalculadas(ctx, plano, produto) if alternativas and d["acao"] == "corrigir_fluxo" else []
    from . import intervencoes
    return {"pedido": pedido, "atividades": atividades, "decisao": d, "sugestoes": sugestoes, "alternativas": alt,
            "intervencoes": intervencoes.do_produto(ctx.db, ctx.empresa_id, plano.produto_id),
            "metodo": ("Leitura por atividade: desvio típico = mediana de ln(realizado ÷ previsto); variabilidade = 1,4826 × MAD. "
                       "Estável (≤ 0,15) e fora de ±10 % → corrigir o padrão; irregular e acima do padrão → corrigir o fluxo "
                       "(causas especiais, Shewhart). Limiares são escolhas do projeto.")}
