"""Provedor local, determinístico e sem rede. Funciona sem chave de API.

Faz o mínimo útil: lê a descrição/respostas, propõe perguntas por grupo, monta um rascunho
de estrutura (etapas a partir do texto) e redige análises a partir de fatos já calculados.
Nunca inventa valores numéricos: parâmetros saem sem valor ("a medir").
"""
from __future__ import annotations

import re
import unicodedata

from .esquemas import (AnaliseTexto, EstruturaProposta, EtapaIA, ListaPerguntas, MaterialIA,
                       OperacaoIA, ParametroIA, PerguntaIA, PontoInvestigacao, ProcessoIA, RecursoIA)

NOME = "heuristica"

BASE = {
    "Processos": ["Quais são as etapas do processo, na ordem em que acontecem?",
                  "Existem caminhos alternativos ou etapas que só ocorrem em alguns casos?"],
    "Recursos": ["Quais máquinas, ferramentas, equipamentos e instalações são utilizados?"],
    "Pessoas": ["Quem executa cada etapa e quantas pessoas participam? Há diferença entre operadores?"],
    "Materiais": ["O que entra em cada etapa e em que quantidade? Existem perdas ou refugos?"],
    "Tempo": ["Quanto tempo leva cada etapa, em média? Há esperas? O que faz o tempo variar?"],
    "Quantidade": ["Quantas unidades, lotes ou peças são processadas por ordem ou por dia?"],
    "Qualidade": ["Quais erros, retrabalhos ou rejeições podem ocorrer e em que etapa?"],
    "Manutenção": ["Existem paradas de máquinas? Como a manutenção é registrada hoje?"],
    "Ergonomia": ["Há esforço físico, repetitividade, postura ou deslocamentos relevantes em alguma etapa?"],
    "Ambiente": ["Existe posto específico, espera, espaço limitado ou condição que influencia a operação?"],
    "Informação": ["Onde o andamento é registrado hoje: sistema, planilha, papel ou comunicação verbal?"],
}

# Perguntas de aprofundamento disparadas por palavras nas respostas/descrição.
GATILHOS = [
    (r"m[aá]quina|cnc|equipamento|forno|serra|prensa|esteira", "Recursos",
     "Para cada máquina citada: qual a capacidade (unidades/hora) e quanto tempo leva a preparação (setup)?"),
    (r"perda|refugo|desperd[ií]cio|sobra", "Materiais",
     "Qual é a porcentagem aproximada de perda ou refugo e em qual etapa ela mais ocorre?"),
    (r"espera|fila|aguard|parad", "Tempo",
     "O que normalmente causa as esperas ou paradas citadas e quanto tempo costumam durar?"),
    (r"retrabalho|refaz|erro|defeito|devolu", "Qualidade",
     "Quando ocorre retrabalho, quem identifica o problema e quanto tempo adicional ele costuma consumir?"),
    (r"atras|prazo", "Processos",
     "Em quais etapas os atrasos mais aparecem e como o prazo prometido ao cliente é definido?"),
    (r"planilha|papel|caderno|whatsapp|verbal", "Informação",
     "Quais informações dessas planilhas/registros (tempos, quantidades, responsáveis) já estão disponíveis para importar?"),
    (r"turno|equipe|time", "Pessoas",
     "Como as equipes/turnos são organizados e algum deles é mais rápido ou mais lento em determinadas etapas?"),
]

LACUNAS = [
    (r"receb|compra|insumo|mat[eé]ria", "Recebimento e conferência de materiais"),
    (r"inspe|confer|qualidade|teste|revis", "Inspeção / conferência de qualidade"),
    (r"entreg|expedi|instal|envio|despach", "Expedição, entrega ou instalação"),
]

INDICADORES = [
    "Tempo planejado x realizado por etapa", "Ordens atrasadas", "Tempo de espera por etapa (gargalos)",
    "Paradas por motivo e duração", "Retrabalho (quantidade e tempo)", "Utilização das máquinas",
    "Produtividade (unidades por hora)", "Refugo / perdas (%)",
]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def _infinitivo(verbo: str) -> str:
    """Converte 1ª pessoa do plural (recebemos, preparamos, produzimos) em infinitivo."""
    v = verbo.lower()
    for suf, novo in (("amos", "ar"), ("emos", "er"), ("imos", "ir"), ("ímos", "ir")):
        if v.endswith(suf) and len(v) > 5:
            return v[: -len(suf)] + novo
    return v


def _cap(s: str) -> str:
    s = s.strip(" .;:-–—")
    return s[:1].upper() + s[1:]


def etapas_do_texto(texto: str) -> list[str]:
    """Extrai etapas de uma descrição ('recebemos insumos, preparamos e entregamos')
    ou de uma lista numerada/com marcadores."""
    texto = texto.replace("→", ",").replace("->", ",")
    if re.search(r"(^|\n)\s*(\d+[.)]|[-•*])\s+\S", texto):
        partes = re.split(r"\n+\s*(?:\d+[.)]|[-•*])?\s*", texto)
    else:
        partes = re.split(r"[,;.\n]|\se\s|\sdepois\s|\sent[aã]o\s|\sem seguida\s", texto)
    etapas, vistos = [], set()
    for p in partes:
        p = re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", p).strip()
        palavras = p.split()
        if len(palavras) < 1 or len(p) < 3:
            continue
        palavras[0] = _infinitivo(palavras[0])
        nome = _cap(" ".join(palavras))[:120]
        if _norm(nome) not in vistos:
            vistos.add(_norm(nome))
            etapas.append(nome)
    return etapas[:20]


def _itens(texto: str) -> list[str]:
    partes = re.split(r"[,;\n]|\se\s", texto)
    out, vistos = [], set()
    for p in partes:
        p = re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", p).strip(" .")
        if 2 <= len(p) <= 120 and _norm(p) not in vistos:
            vistos.add(_norm(p))
            out.append(_cap(p))
    return out[:30]


def _tipo_recurso(nome: str) -> str:
    n = _norm(nome)
    if re.search(r"posto|bancada|estacao|balcao|mesa", n):
        return "posto"
    if re.search(r"ferramenta|furadeira|parafusadeira|faca|serrote", n):
        return "ferramenta"
    if re.search(r"sala|camara|galpao|area|cabine|estufa", n):
        return "instalacao"
    return "maquina"


def gerar_perguntas(ctx: dict) -> ListaPerguntas:
    """ctx: descricao, objetivo, problemas, qa=[{grupo,texto,resposta}], max."""
    qa = ctx.get("qa", [])
    feitas = {_norm(q["texto"]) for q in qa}
    grupos_resp = {q["grupo"] for q in qa if (q.get("resposta") or "").strip()}
    grupos_perg = {q["grupo"] for q in qa}
    texto_total = " ".join([ctx.get("descricao", ""), ctx.get("problemas", ""), ctx.get("objetivo", "")] +
                           [q.get("resposta") or "" for q in qa])
    out: list[PerguntaIA] = []
    # 1) aprofundamentos disparados pelo conteúdo
    for padrao, grupo, texto in GATILHOS:
        if re.search(padrao, _norm(texto_total)) and _norm(texto) not in feitas:
            out.append(PerguntaIA(grupo=grupo, texto=texto))
    # 2) cobrir grupos ainda sem pergunta
    for grupo, textos in BASE.items():
        if grupo not in grupos_perg:
            out += [PerguntaIA(grupo=grupo, texto=t) for t in textos if _norm(t) not in feitas]
    # 3) grupos perguntados e ainda sem resposta não geram duplicatas
    del grupos_resp
    return ListaPerguntas(perguntas=out[: ctx.get("max", 12)])


def estruturar(ctx: dict) -> EstruturaProposta:
    qa = ctx.get("qa", [])
    resp = lambda g: " \n".join((q.get("resposta") or "") for q in qa if q["grupo"] == g).strip()  # noqa: E731
    fonte_etapas = resp("Processos") or ctx.get("descricao", "")
    nomes = etapas_do_texto(fonte_etapas)
    recursos_txt = _itens(resp("Recursos"))
    materiais_txt = _itens(resp("Materiais"))

    recursos = [RecursoIA(nome=r, tipo=_tipo_recurso(r)) for r in recursos_txt]
    etapas = []
    for n in nomes:
        etapas.append(EtapaIA(
            nome=n, operacoes=[OperacaoIA(
                nome=n, recurso=None,
                parametros=[
                    ParametroIA(nome="tempo_preparacao_min", unidade="min",
                                justificativa="A medir: tempo de preparação informado/medido pela empresa."),
                    ParametroIA(nome="tempo_unitario_min", unidade="min/un",
                                justificativa="A medir: tempo de execução por unidade."),
                ])]))
    base_texto = _norm(" ".join([ctx.get("descricao", "")] + [q.get("resposta") or "" for q in qa]))
    omitidas = [nome for padrao, nome in LACUNAS if not re.search(padrao, base_texto)]
    todas = {g for g in BASE}
    respondidos = {q["grupo"] for q in qa if (q.get("resposta") or "").strip()}
    pend = [f"Grupo '{g}' ainda sem resposta." for g in BASE if g in todas and g not in respondidos]
    macro = f"Fluxo principal – {ctx.get('unidade', 'operação')}"
    proc = ProcessoIA(nome=f"Processo principal – {ctx.get('unidade', 'operação')}", macroprocesso=macro,
                      descricao=(ctx.get("descricao", "") or "")[:2000], etapas=etapas)
    return EstruturaProposta(
        processos=[proc] if etapas else [], recursos=recursos,
        materiais=[MaterialIA(nome=m) for m in materiais_txt], indicadores_sugeridos=INDICADORES,
        etapas_possivelmente_omitidas=omitidas, perguntas_pendentes=pend,
        observacoes=("Rascunho gerado por regras locais (sem IA externa) a partir do texto informado. "
                     "Revise nomes, ordem e vínculos de recursos antes de ativar. Nenhum tempo foi estimado."))


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
    if tipo == "indicadores_sugeridos":
        return AnaliseTexto(resumo="Indicadores sugeridos a partir do perfil da operação.",
                            indicadores_sugeridos=INDICADORES)
    if tipo == "processos_semelhantes":
        pts = [PontoInvestigacao(titulo=f"{g['a']} ≈ {g['b']}", evidencia=g["motivo"]) for g in fatos.get("pares", [])]
        return AnaliseTexto(resumo=f"{len(pts)} par(es) de operações com nomes semelhantes encontrados.",
                            pontos_investigacao=pts)
    return AnaliseTexto(resumo="Tipo de análise não suportado.")
