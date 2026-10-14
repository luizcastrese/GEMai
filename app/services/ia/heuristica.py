"""Provedor local, determinístico e sem rede. Funciona sem chave de API.

Faz o mínimo útil: lista as peças de um item descrito em texto, monta o plano de trabalho por regras e
redige análises a partir de fatos já calculados. Nunca inventa valores numéricos: o que falta vira pendência.
"""
from __future__ import annotations

import re
import unicodedata

import math

from ..modelo_tempo import MOVIMENTOS_MOST, REFERENCIAS, TMU_MIN, ElementoTempo
from .esquemas import AnaliseTexto, ComponenteIA, EstruturaProdutoIA, PassoIA, PlanoProposta, PontoInvestigacao

NOME = "heuristica"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def _cap(s: str) -> str:
    s = s.strip(" .;:-–—")
    return s[:1].upper() + s[1:]


def _fmt(v, suf=" min"):
    return "n/d" if v is None else f"{v:g}{suf}"


def analisar(tipo: str, fatos: dict) -> AnaliseTexto:
    if tipo == "analise_desvio":
        r, ops = fatos["resumo"], fatos["operacoes"]
        pts = []
        for m in sorted([m for m in ops if m.get("desvio_min")], key=lambda m: -abs(m["desvio_min"]))[:3]:
            sentido = "acima" if m["desvio_min"] > 0 else "abaixo"
            pts.append(PontoInvestigacao(
                titulo=f"{m['operacao']} ({m['etapa']})",
                evidencia=f"Realizado {_fmt(m['realizado_min'])} vs estimado {_fmt(m['estimado_min'])} "
                          f"({_fmt(m['desvio_pct'], '%')} {sentido} do previsto).",
                hipotese="Possível influência de: " + ", ".join(
                    x for x in [
                        f"retrabalho de {_fmt(m['retrabalho_min'])}" if m["retrabalho_min"] else "",
                        f"espera registrada de {_fmt(m['espera_min'])}" if m["espera_min"] else "",
                        f"fila antes da operação de {_fmt(m['espera_fila_min'])}" if m["espera_fila_min"] else "",
                        f"refugo de {m['qtd_refugo']:g} un" if m["qtd_refugo"] else "",
                        "estimativa baseada só em parâmetro (sem histórico)" if m["fonte_estimativa"] == "parametro" else "",
                    ] if x) or "nenhum fator registrado – investigar no local"))
        for o in fatos.get("ocorrencias", []):
            if o["tipo"] == "parada" and (o["duracao_min"] or 0) > 0:
                pts.append(PontoInvestigacao(titulo=f"Parada: {o['causa']}",
                                             evidencia=f"Duração de {_fmt(o['duracao_min'])}.",
                                             hipotese="Verificar se a causa se repete em outras ordens."))
        resumo = (f"Ordem {fatos['ordem']['numero']}: realizado {_fmt(r['realizado_min'])} contra "
                  f"{_fmt(r['estimado_min'])} estimados (desvio {_fmt(r['desvio_pct'], '%')}; eficiência "
                  f"{_fmt(r['eficiencia_pct'], '%')}). ")
        if r.get("comparacao_parcial") or r.get("operacoes_sem_estimativa"):
            resumo += "A comparação é parcial: há operações sem estimativa. "
        resumo += "Os pontos abaixo são sugestões para investigação, não conclusões."
        return AnaliseTexto(resumo=resumo, pontos_investigacao=pts)
    if tipo == "analise_gargalo":
        g = fatos.get("gargalos", [])[:3]
        pts = [PontoInvestigacao(
            titulo=f"Etapa {x['etapa']}",
            evidencia=f"Fila {_fmt(x['espera_fila_min'])}, espera registrada {_fmt(x['espera_registrada_min'])}, "
                      f"ocupação {_fmt(x['ocupacao_min'])}.",
            hipotese="Pode indicar capacidade insuficiente ou desbalanceamento da etapa anterior.") for x in g]
        return AnaliseTexto(resumo="Etapas com maior espera acumulada no período (candidatas a gargalo): "
                            + (", ".join(x["etapa"] for x in g) or "nenhuma identificada") + ".",
                            pontos_investigacao=pts)
    if tipo == "relatorio_gestor":
        o, pxr, par, ret, qual = (fatos["ordens"], fatos["planejado_x_realizado"], fatos["paradas"],
                                  fatos["retrabalho"], fatos["qualidade"])
        linhas = [f"{o['em_producao']} ordem(ns) em aberto; {len(fatos['ordens_atrasadas'])} atrasada(s).",
                  f"Eficiência (previsto/realizado): {_fmt(pxr['eficiencia_pct'], '%')}.",
                  f"Paradas somaram {_fmt(par['total_min'])}.",
                  f"Retrabalho consumiu {_fmt(ret['tempo_min'])}; refugo de {_fmt(qual['refugo_pct'], '%')}."]
        pts = [PontoInvestigacao(titulo=f"{d['operacao']} ({d['etapa']})",
                                 evidencia=f"Desvio de {_fmt(d['desvio_pct'], '%')} no período.")
               for d in pxr["maiores_desvios"][:3]]
        return AnaliseTexto(resumo=" ".join(linhas), pontos_investigacao=pts)
    return AnaliseTexto(resumo="Tipo de análise não suportado.")


# ---------------------------------------------------------------- produto: lista de componentes a partir de texto
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
        "oito": 8, "nove": 9, "dez": 10, "doze": 12}
_FERRAGEM = r"dobradi|corredi|puxador|parafuso|cavilha|minifix|prego|pino|suporte|rodizio|rodízio|trilho|fechadura"
_MATERIAIS = ("mdf", "mdp", "compensado", "pinus", "madeira", "aço", "aco", "alumínio", "aluminio", "vidro")


def interpretar_produto(ctx: dict) -> EstruturaProdutoIA:
    """Extrai 'N componente' de uma descrição. Não inventa medidas: devolve só nomes e quantidades."""
    texto = ctx.get("descricao", "")
    mat = next((m for m in _MATERIAIS if m in _norm(texto)), "")
    partes = re.split(r"[,;\n]|\se\s|\scom\s|\s\+\s", texto)
    comps, vistos, faltam = [], set(), []
    for p in partes:
        p = p.strip(" .-•*")
        m = re.match(r"^(\d+(?:[.,]\d+)?|[a-zA-ZÀ-ú]+)\s*(?:x|un\.?|unidades?|de)?\s+(.+)$", p)
        qtd, nome = 1.0, p
        if m:
            tok = m.group(1).lower()
            if tok in _NUM:
                qtd, nome = float(_NUM[tok]), m.group(2)
            elif re.match(r"^\d", tok):
                qtd, nome = float(tok.replace(",", ".")), m.group(2)
        nome = _cap(re.sub(r"^(armário|armario|móvel|movel)\s+(de|com)\s+", "", nome.strip(), flags=re.I))
        if len(nome) < 3 or _norm(nome) in vistos or _norm(nome) in ("armario", "movel") or _norm(nome) in _MATERIAIS:
            continue
        vistos.add(_norm(nome))
        ferragem = bool(re.search(_FERRAGEM, _norm(nome)))
        grupo = ("Ferragens" if ferragem else "Porta" if re.search(r"porta", _norm(nome))
                 else "Gaveta" if re.search(r"gaveta", _norm(nome)) else "Corpo")
        comps.append(ComponenteIA(nome=nome, quantidade=qtd, material="" if ferragem else mat, grupo=grupo))
    if comps:
        faltam = ["Medidas de cada peça (comprimento, largura e espessura)", "Como cada componente se liga aos outros (método e nº de fixadores)"]
    return EstruturaProdutoIA(componentes=comps, ligacoes=[], dados_faltantes=faltam,
                              observacoes="Lista extraída do texto por regras locais: confira nomes e quantidades e complete as medidas.")


# ---------------------------------------------------------------- plano de trabalho (heurística local)
_POS_IDX = MOVIMENTOS_MOST["levantamento_curvado"] + MOVIMENTOS_MOST["posicionamento_preciso"]
POS_MIN = sum(_POS_IDX) * 10 * TMU_MIN  # minutos para pegar e posicionar uma peça (índices MOST ilustrativos)


def planejar(ctx: dict) -> PlanoProposta:
    """Plano a partir dos componentes, das ligações e do contorno físico. Regras e referências declaradas;
    o que faltar vira `dados_faltantes` (nunca um tempo inventado em silêncio)."""
    N = float(ctx["produto"]["quantidade"])
    comps, ligs = ctx["componentes"], ctx["ligacoes"]
    refs = ctx["referencias"]
    pessoas_eq = max(int(ctx.get("pessoas") or 1), 1)
    carga_ref = float(ctx.get("carga_ref_kg") or REFERENCIAS["carga_manual_max_kg"])  # limite de carga por pessoa (depende do perfil)
    espacos, recursos = ctx.get("espacos", []), ctx.get("recursos", [])
    prem: list[str] = []
    faltam: list[str] = []
    passos: list[PassoIA] = []

    def achar_local(tipo: str, palavra: str):
        return next((e["nome"] for e in espacos if e.get("tipo") == tipo), None) or \
            next((e["nome"] for e in espacos if palavra in _norm(e["nome"])), None)

    estoque, montagem = achar_local("estoque", "estoque"), achar_local("montagem", "montag")
    if not estoque:
        faltam.append("Local de estoque (onde as peças ficam antes de cortar)")
    if not montagem:
        faltam.append("Local de montagem")

    def equip(funcao: str):
        lista = [r for r in recursos if r.get("funcao") == funcao]
        return next((r for r in lista if r.get("capacidade_un_h")), lista[0] if lista else None)

    def pessoas_para(peso):
        return max(pessoas_eq, math.ceil(peso / carga_ref)) if peso else pessoas_eq

    def mover(origem, destino, nomes, pecas, peso, titulo):
        if not origem or not destino or origem == destino:
            return
        pes = pessoas_para(peso)
        itens = max(int(carga_ref * pes // peso), 1) if peso else 1
        passos.append(PassoIA(nome=titulo, tipo="movimentacao", componentes=nomes, qtd_pecas=pecas, espaco_origem=origem, espaco_destino=destino,
                              pessoas=pes, elementos=[ElementoTempo(
                                  nome=f"Levar de {origem} até {destino}", tipo="deslocamento", metodo="deslocamento",
                                  velocidade_m_min=REFERENCIAS["velocidade_caminhada_m_min"], itens_por_viagem=itens, ida_e_volta=True,
                                  justificativa=f"{itens} peça(s) por viagem (carga manual de referência: {carga_ref:g} kg por pessoa).")]))

    paineis = [c for c in comps if c.get("comp") and c.get("larg")]
    pesos = [c["peso_kg"] for c in paineis if c.get("peso_kg")]
    peso_medio = sum(pesos) / len(pesos) if pesos else None
    for c in comps:
        if c.get("peso_origem") == "estimado":
            prem.append(f"Peso de '{c['nome']}' estimado por material e medidas ({c['peso_kg']:.1f} kg): informe o real.")
        elif c.get("peso_kg") is None and (c.get("comp") and c.get("larg")):
            faltam.append(f"Peso de '{c['nome']}' (informe o peso ou o material e a espessura)")

    # --- usinagem: cortar, colar borda, furar (nessa ordem), com a movimentação entre os locais
    local_atual = estoque
    etapas_maq = (("corte", "Cortar", lambda c: True), ("bordo", "Colar borda", lambda c: (c.get("bordas_m") or 0) > 0),
                  ("furacao", "Furar", lambda c: (c.get("furos") or 0) > 0))
    for funcao, verbo, filtro in etapas_maq:
        alvo = [c for c in paineis if filtro(c)]
        if not alvo:
            continue
        pecas = sum(c["qtd"] for c in alvo) * N
        nomes = [c["nome"] for c in alvo]
        eq = equip(funcao)
        if eq is None:
            faltam.append(f"Equipamento para '{verbo.lower()}' (informe a máquina na seção Agentes do item)")
            passos.append(PassoIA(nome=f"{verbo} {pecas:g} peças", tipo=funcao, componentes=nomes, qtd_pecas=pecas))
            continue
        mover(local_atual, eq.get("espaco"), nomes, pecas, peso_medio, f"Levar peças até {eq.get('espaco')} ({verbo.lower()})")
        local_atual = eq.get("espaco") or local_atual
        els = [ElementoTempo(nome=f"Preparar {eq['nome']}", tipo="preparacao", metodo="fixo", a_min=REFERENCIAS["preparacao_maquina_min"],
                             justificativa="Referência genérica de preparação; meça a sua."),
               ElementoTempo(nome=f"{verbo} em {eq['nome']}", tipo="processamento", metodo="capacidade_recurso", depende_operador=False,
                             justificativa="Capacidade (peças por hora) informada para o equipamento.")]
        if not eq.get("capacidade_un_h"):
            faltam.append(f"Quantas peças por hora faz '{eq['nome']}'")
        passos.append(PassoIA(nome=f"{verbo} {pecas:g} peça(s)", tipo=funcao, componentes=nomes, qtd_pecas=pecas, recurso=eq["nome"],
                              espaco_origem=eq.get("espaco"), espaco_destino=eq.get("espaco"), pessoas=pessoas_eq, elementos=els))
    mover(local_atual, montagem, [c["nome"] for c in paineis], sum(c["qtd"] for c in paineis) * N, peso_medio, "Levar peças até a montagem")

    # --- montagem por subconjunto e final
    grupo_de = {c["nome"]: c.get("grupo") or "Corpo" for c in comps}
    grupos = list(dict.fromkeys(grupo_de.values()))

    def elementos_montagem(lista_ligs, n_pecas, rotulo):
        els = []
        if n_pecas:
            els.append(ElementoTempo(nome=f"Pegar e posicionar {n_pecas:g} peça(s)/conjunto(s) por unidade", tipo="manuseio", metodo="fixo", por_unidade=True,
                                     a_min=round(n_pecas * POS_MIN, 4),
                                     justificativa=f"{len(_POS_IDX)} índices MOST ilustrativos (≈{POS_MIN * 60:.0f} s por peça): curvar/levantar + posicionar com cuidado."))
        por_metodo: dict[str, int] = {}
        for l in lista_ligs:
            por_metodo[l["metodo"]] = por_metodo.get(l["metodo"], 0) + int(l.get("fixadores") or 0)
        for metodo, n in por_metodo.items():
            if n <= 0:
                continue
            chave = f"fixador:{metodo}" if f"fixador:{metodo}" in refs else "fixador:outro"
            origem = "da sua oficina" if chave in ctx.get("referencias_informadas", []) else "genérico"
            els.append(ElementoTempo(nome=f"Fixar com {metodo} ({n} un por unidade)", tipo="processamento", metodo="fixo", por_unidade=True,
                                     a_min=round(n * refs[chave], 4), justificativa=f"{refs[chave]:g} min por {metodo} ({origem})."))
        return els

    for g in grupos:
        membros = [c for c in comps if (c.get("grupo") or "Corpo") == g]
        nomes = [c["nome"] for c in membros]
        l_g = [l for l in ligs if grupo_de.get(l["componente"]) == g and (not l.get("ligado_a") or grupo_de.get(l["ligado_a"]) == g)]
        pecas_g = sum(c["qtd"] for c in membros if c.get("comp") and c.get("larg"))
        if not pecas_g and not l_g:
            continue
        if not l_g:
            faltam.append(f"Como se montam as peças do grupo '{g}' (método e nº de fixadores)")
        pesos_g = [c["peso_kg"] for c in membros if c.get("peso_kg")]
        passos.append(PassoIA(nome=f"Montar {g}", tipo="montagem", grupo=g, componentes=nomes, qtd_pecas=N, espaco_origem=montagem, espaco_destino=montagem,
                              pessoas=pessoas_para(max(pesos_g) if pesos_g else None), elementos=elementos_montagem(l_g, pecas_g, g)))
    l_final = [l for l in ligs if l.get("ligado_a") and grupo_de.get(l["componente"]) != grupo_de.get(l["ligado_a"])]
    if l_final or len(grupos) > 1:
        if not l_final:
            faltam.append("Como os subconjuntos se ligam na montagem final (método e nº de fixadores)")
        peso_conj = sum((c.get("peso_kg") or 0) * c["qtd"] for c in comps)
        passos.append(PassoIA(nome="Montagem final", tipo="montagem", grupo="Final", componentes=[g for g in grupos], qtd_pecas=N,
                              espaco_origem=montagem, espaco_destino=montagem, pessoas=pessoas_para(peso_conj or None),
                              elementos=elementos_montagem(l_final, max(len(grupos) - 1, 1), "final")))
    passos.append(PassoIA(nome="Conferência final", tipo="inspecao", qtd_pecas=N, espaco_origem=montagem, espaco_destino=montagem, pessoas=1,
                          elementos=[ElementoTempo(nome="Conferir acabamento, folgas e funcionamento", tipo="inspecao", metodo="fixo", por_unidade=True,
                                                   a_min=refs["conferencia_final"], justificativa="Referência genérica; ajuste ao seu padrão de qualidade.")]))
    prem.append("Pressupõe uma equipe executando os passos em sequência (sem trabalho em paralelo entre passos).")
    prem.append("Tempos de montagem e conferência partem de referências genéricas (ou da sua tabela); movimentação usa caminhada a "
                f"{REFERENCIAS['velocidade_caminhada_m_min']:g} m/min. Substitua por medições assim que existirem.")
    return PlanoProposta(passos=passos, premissas=prem, dados_faltantes=list(dict.fromkeys(faltam)), confianca="baixa",
                         justificativa="Plano montado por regras locais a partir dos componentes, ligações e contorno físico cadastrados.")
