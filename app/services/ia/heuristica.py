"""Provedor local, determinístico e sem rede. Funciona sem chave de API.

Faz o mínimo útil: lê a descrição/respostas, propõe perguntas por grupo, monta um rascunho
de estrutura (etapas a partir do texto) e redige análises a partir de fatos já calculados.
Nunca inventa valores numéricos: parâmetros saem sem valor ("a medir").
"""
from __future__ import annotations

import re
import unicodedata

import math

from ..modelo_tempo import MOVIMENTOS_MOST, REFERENCIAS, TMU_MIN, ElementoTempo, ModeloTempoIA, ToleranciaTempo
from .esquemas import (AnaliseTexto, ComponenteIA, EspacoIA, EstruturaProdutoIA, EstruturaProposta, PassoIA, PlanoProposta, EtapaIA, ListaPerguntas, MaterialIA,
                       OperacaoIA, ParametroIA, PerguntaIA, PontoInvestigacao, ProcessoIA, RecursoIA)

NOME = "heuristica"

BASE = {
    "Processos": ["Quais são as etapas do processo, na ordem em que acontecem?",
                  "Existem caminhos alternativos ou etapas que só ocorrem em alguns casos?"],
    "Recursos": ["Quais máquinas, ferramentas, equipamentos e instalações são utilizados?",
                 "Para cada máquina, quantas peças ou unidades ela faz por hora, mais ou menos?"],
    "Pessoas": ["Quem executa cada etapa e quantas pessoas participam? Há diferença entre operadores?"],
    "Materiais": ["O que entra em cada etapa e em que quantidade? Existem perdas ou refugos?",
                  "Quanto pesa, em média, cada peça ou material que as pessoas carregam?"],
    "Tempo": ["Quanto tempo leva cada etapa, em média? Há esperas? O que faz o tempo variar?"],
    "Quantidade": ["Quantas unidades, lotes ou peças são processadas por ordem ou por dia?"],
    "Qualidade": ["Quais erros, retrabalhos ou rejeições podem ocorrer e em que etapa?"],
    "Manutenção": ["Existem paradas de máquinas? Como a manutenção é registrada hoje?"],
    "Ergonomia": ["Há esforço físico, repetitividade, postura ou deslocamentos relevantes em alguma etapa?"],
    "Ambiente": ["Existe posto específico, espera, espaço limitado ou condição que influencia a operação?",
                 "Quais são os lugares por onde o material passa (ex.: estoque, bancada de corte, montagem, expedição)?"],
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
    # locais: só da pergunta específica; descarta itens com números (ex.: "estoque a 20 m")
    locais_txt = [x for q in qa if q["texto"].startswith("Quais são os lugares") for x in _itens(q.get("resposta") or "")
                  if not re.search(r"\d", x)]
    recursos_txt = [x for q in qa if q["grupo"] == "Recursos" and q["texto"].startswith("Quais máquinas")
                    for x in _itens(q.get("resposta") or "")] or _itens(resp("Recursos"))
    materiais_txt = [x for q in qa if q["grupo"] == "Materiais" and q["texto"].startswith("O que entra")
                     for x in _itens(q.get("resposta") or "")]

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
                ],
                inicio_marco=f"Quando a primeira unidade de '{n}' é iniciada",
                fim_marco=f"Quando a última unidade de '{n}' é concluída e liberada para a próxima etapa")]))
    base_texto = _norm(" ".join([ctx.get("descricao", "")] + [q.get("resposta") or "" for q in qa]))
    omitidas = [nome for padrao, nome in LACUNAS if not re.search(padrao, base_texto)]
    todas = {g for g in BASE}
    respondidos = {q["grupo"] for q in qa if (q.get("resposta") or "").strip()}
    pend = [f"Grupo '{g}' ainda sem resposta." for g in BASE if g in todas and g not in respondidos]
    macro = f"Fluxo principal – {ctx.get('unidade', 'operação')}"
    proc = ProcessoIA(nome=f"Processo principal – {ctx.get('unidade', 'operação')}", macroprocesso=macro,
                      descricao=(ctx.get("descricao", "") or "")[:2000], etapas=etapas)
    return EstruturaProposta(
        processos=[proc] if etapas else [], recursos=recursos, espacos=[EspacoIA(nome=n) for n in locais_txt[:20]],
        materiais=[MaterialIA(nome=m) for m in materiais_txt], indicadores_sugeridos=INDICADORES,
        etapas_possivelmente_omitidas=omitidas, perguntas_pendentes=pend,
        observacoes=("Rascunho gerado por regras locais (sem IA externa) a partir do texto informado. "
                     "Revise nomes, ordem e vínculos de recursos antes de ativar. Nenhum tempo foi estimado."))


def modelar(ctx: dict) -> ModeloTempoIA:
    """Modelo de tempo por regras e referências declaradas (confiança baixa). Nunca chuta o que falta:
    lista o dado do contorno físico necessário. Sexo/estatura/peso corporal NÃO alteram o tempo; o perfil
    contribui com o ritmo (calibrado) e com limites de carga/ergonomia calculados pelo sistema."""
    op, rec, item = ctx["operacao"], ctx.get("recurso"), ctx.get("item", {})
    org, dst, dist = ctx.get("espaco_origem"), ctx.get("espaco_destino"), ctx.get("distancia_m")
    perfil, erg = ctx.get("perfil"), ctx.get("ergonomia_calculada") or {}
    pessoas = max(int(op.get("num_pessoas") or 1), 1)
    peso = item.get("peso_kg")
    mov = op.get("tipo_movimento") or ""
    els: list[ElementoTempo] = []
    faltam: list[str] = []
    prem: list[str] = []
    if rec:
        prep = REFERENCIAS["preparacao_maquina_min"] if rec.get("tipo") in ("maquina", "ferramenta") else REFERENCIAS["preparacao_posto_min"]
        els.append(ElementoTempo(nome=f"Preparação de {rec['nome']}", tipo="preparacao", metodo="fixo", a_min=prep,
                                 justificativa="Valor de referência genérico; meça o setup real da sua operação."))
        prem.append(f"Preparação de {prep:g} min por ordem é uma referência genérica, não um dado da empresa.")
        if rec.get("capacidade_un_h"):
            els.append(ElementoTempo(nome=f"Processamento em {rec['nome']}", tipo="processamento", metodo="capacidade_recurso",
                                     depende_operador=False, justificativa="Usa a capacidade informada do equipamento (tempo de máquina)."))
        else:
            faltam.append(f"Capacidade (un/h) do equipamento '{rec['nome']}'")
    if (org or dst) and not (org and dst and org.get('nome') == dst.get('nome') and not dist):
        if dist is not None:
            itens = max(int(REFERENCIAS["carga_manual_max_kg"] * pessoas // peso), 1) if peso else 1
            els.append(ElementoTempo(nome=f"Deslocar de {org['nome'] if org else '?'} até {dst['nome'] if dst else '?'}",
                                     tipo="deslocamento", metodo="deslocamento", velocidade_m_min=REFERENCIAS["velocidade_caminhada_m_min"],
                                     itens_por_viagem=itens, ida_e_volta=True,
                                     justificativa=f"{dist:g} m entre os espaços; {itens} item(ns) por viagem."))
            prem.append(f"Caminhada a {REFERENCIAS['velocidade_caminhada_m_min']:g} m/min e carga manual de até "
                        f"{REFERENCIAS['carga_manual_max_kg']:g} kg por pessoa (referências genéricas).")
        else:
            faltam.append("Distância entre os espaços de origem e destino" if org and dst else "Espaço de origem e de destino da operação")
    if mov in MOVIMENTOS_MOST:
        els.append(ElementoTempo(nome=f"Movimento: {mov.replace('_', ' ')}", tipo="manuseio", metodo="indices_most", por_unidade=True,
                                 indices_most=MOVIMENTOS_MOST[mov], paralelizavel=pessoas > 1,
                                 justificativa="Sequência General Move (A B G A B P A) com índices ilustrativos; conferir com o cartão MOST certificado."))
        prem.append("Tempo de movimento por índices no estilo BasicMOST (1 TMU = 0,036 s); índices ilustrativos para o tipo de movimento informado.")
    elif peso:
        els.append(ElementoTempo(nome="Manuseio do item", tipo="manuseio", metodo="linear_driver", por_unidade=True,
                                 driver="peso_kg", a_min=REFERENCIAS["manuseio_base_min"], b_min=REFERENCIAS["manuseio_min_por_kg"],
                                 paralelizavel=pessoas > 1,
                                 justificativa="Pegar, posicionar e soltar: tempo-base mais acréscimo proporcional ao peso."))
        prem.append("Manuseio: 0,15 min + 0,012 min/kg por unidade (referência genérica).")
        if mov:
            faltam.append(f"Índices de movimento (MOST) para o tipo '{mov}'")
    elif not rec or not rec.get("capacidade_un_h"):
        faltam.append("Peso e dimensões do item manuseado, ou o tipo de movimento")
    if not els:
        faltam.append("Equipamento/posto ou espaços e item físico da operação")

    # Tolerâncias (tempo padrão = tempo normal × FT). Percentuais da OIT sem distinção por sexo.
    tol = [{"categoria": "necessidades pessoais", "percentual": REFERENCIAS["tolerancia_pessoal_pct"],
            "justificativa": "Tolerância constante para necessidades pessoais.", "fonte": "OIT (Estudo do Trabalho)"},
           {"categoria": "fadiga básica", "percentual": REFERENCIAS["fadiga_basica_pct"],
            "justificativa": "Tolerância constante de fadiga básica.", "fonte": "OIT (Estudo do Trabalho)"}]
    if op.get("postura_trabalho") == "em_pe":
        tol.append({"categoria": "trabalho em pé", "percentual": REFERENCIAS["em_pe_pct"], "justificativa": "Postura em pé.", "fonte": "OIT (Estudo do Trabalho)"})
    tol += erg.get("tolerancias_sugeridas", [])
    for a in erg.get("alertas", []):
        prem.append(f"Alerta ergonômico: {a}")
    amb = [e for e in (org, dst) if e]
    for e in amb:
        if e.get("temperatura_c") is not None and (e["temperatura_c"] > 30 or e["temperatura_c"] < 12):
            faltam.append(f"Avaliar tolerância para temperatura ({e['temperatura_c']:g} °C em '{e['nome']}') — NR-15/NHO-06 e conforto térmico")
    if perfil:
        prem.append(f"Perfil de mão de obra '{perfil['nome']}': ritmo {perfil['ritmo_pct']:g}%. Sexo, estatura e peso corporal NÃO alteram o tempo; "
                    "são usados só em limites de carga e conferências ergonômicas. Calibre o ritmo com medições.")
    else:
        faltam.append("Perfil de mão de obra (ritmo e limites de carga)")
    if not op.get("funcao_requerida"):
        faltam.append("Função (mão de obra) responsável pela operação")
    if not op.get("inicio_marco") or not op.get("fim_marco"):
        faltam.append("Marcos de início e fim do apontamento (quando começa e quando termina a operação)")
    nome = op["nome"]
    return ModeloTempoIA(
        elementos=els, fator_ambiente=1.0, ritmo_pct=(perfil or {}).get("ritmo_pct") or 100.0,
        tolerancias=[ToleranciaTempo(**t) for t in tol], premissas=prem, dados_faltantes=faltam,
        padrao_apontamento_inicio=op.get("inicio_marco") or f"Quando {op.get('funcao_requerida') or 'o operador'} pega o primeiro item de '{nome}'",
        padrao_apontamento_fim=op.get("fim_marco") or f"Quando o último item de '{nome}' é depositado no destino{' (' + dst['nome'] + ')' if dst else ''}",
        unidade_contagem=op.get("unidade_medida") or "un", confianca="baixa",
        justificativa=("Modelo montado por regras locais a partir do contorno físico cadastrado, com referências declaradas nas premissas. "
                       "Substitua por medições reais assim que existirem."))


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
    if tipo == "revisao_processo":
        r = fatos["prontidao"]
        pts = []
        for o in r["operacoes"]:
            graves = [i for i in o["itens"] if i["nivel"] == "atencao"]
            if graves:
                pts.append(PontoInvestigacao(titulo=o["nome"], evidencia="; ".join(i["msg"] for i in graves[:4]),
                                             hipotese="Sem isso o tempo planejado fica menos consistente e a comparação com o real perde valor."))
        return AnaliseTexto(
            resumo=f"Prontidão do processo para o gêmeo digital: {r['pontuacao_pct']:g}% das operações sem pendências de atenção. "
                   + ("Priorize os pontos abaixo antes de publicar." if pts else "Nenhuma pendência de atenção."),
            pontos_investigacao=pts[:10])
    if tipo == "indicadores_sugeridos":
        return AnaliseTexto(resumo="Indicadores sugeridos a partir do perfil da operação.",
                            indicadores_sugeridos=INDICADORES)
    if tipo == "processos_semelhantes":
        pts = [PontoInvestigacao(titulo=f"{g['a']} ≈ {g['b']}", evidencia=g["motivo"]) for g in fatos.get("pares", [])]
        return AnaliseTexto(resumo=f"{len(pts)} par(es) de operações com nomes semelhantes encontrados.",
                            pontos_investigacao=pts)
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
        return max(pessoas_eq, math.ceil(peso / REFERENCIAS["carga_manual_max_kg"])) if peso else pessoas_eq

    def mover(origem, destino, nomes, pecas, peso, titulo):
        if not origem or not destino or origem == destino:
            return
        pes = pessoas_para(peso)
        itens = max(int(REFERENCIAS["carga_manual_max_kg"] * pes // peso), 1) if peso else 1
        passos.append(PassoIA(nome=titulo, tipo="movimentacao", componentes=nomes, qtd_pecas=pecas, espaco_origem=origem, espaco_destino=destino,
                              pessoas=pes, elementos=[ElementoTempo(
                                  nome=f"Levar de {origem} até {destino}", tipo="deslocamento", metodo="deslocamento",
                                  velocidade_m_min=REFERENCIAS["velocidade_caminhada_m_min"], itens_por_viagem=itens, ida_e_volta=True,
                                  justificativa=f"{itens} peça(s) por viagem (carga manual de referência: {REFERENCIAS['carga_manual_max_kg']:g} kg por pessoa).")]))

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
