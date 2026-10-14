"""Trilha guiada da operação: Atividades → Entradas → Agentes transformadores → Ambiente → Plano.

A plataforma conduz a pessoa por uma sequência fixa. Cada etapa só libera a seguinte quando não restam
pendências, e as pendências são calculadas aqui (uma única fonte de verdade para a tela e para a API).

  1. Atividades  – o que a operação faz com o produto (transporte, corte, borda, furação, montagem, conferência).
  2. Entradas    – o que entra: produto, peças, material, medidas, pesos e como as peças se ligam.
  3. Agentes     – quem/o que transforma as entradas: pessoas (equipe e horário) e a máquina de cada atividade.
  4. Ambiente    – onde acontece: locais, em que local fica cada máquina e a distância entre os locais.

Cada atividade declara o que exige de cada dimensão, e as etapas seguintes cobram só o que as atividades escolhidas pedem.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Componente, Ligacao, Ordem, PlanoTrabalho, Produto, Recurso, Espaco, Unidade
from . import contorno, plano as svc_plano

# código, título, o que é, função do equipamento que a executa (None = feita por pessoas), exigências por dimensão
ATIVIDADES: list[dict] = [
    {"codigo": "movimentacao", "titulo": "Transporte interno", "descricao": "Levar as peças de um local para outro (estoque → máquinas → montagem).",
     "funcao": None, "entradas": "Peso das peças", "agentes": "Pessoas (carga manual)", "ambiente": "Locais e distância entre eles"},
    {"codigo": "corte", "titulo": "Corte", "descricao": "Cortar as chapas nas medidas das peças.",
     "funcao": "corte", "entradas": "Peças com comprimento e largura", "agentes": "Máquina de corte e quantas peças por hora faz", "ambiente": "Local da máquina"},
    {"codigo": "bordo", "titulo": "Colagem de borda", "descricao": "Colar a fita de borda nas peças.",
     "funcao": "bordo", "entradas": "Metros de borda por peça", "agentes": "Coladeira de borda e peças por hora", "ambiente": "Local da máquina"},
    {"codigo": "furacao", "titulo": "Furação", "descricao": "Fazer os furos das peças.",
     "funcao": "furacao", "entradas": "Furos por peça", "agentes": "Furadeira/CNC e peças por hora", "ambiente": "Local da máquina"},
    {"codigo": "montagem", "titulo": "Montagem", "descricao": "Juntar peças e ferragens até formar o produto.",
     "funcao": None, "entradas": "Como as peças se ligam (parafusos, cavilhas…)", "agentes": "Pessoas da equipe", "ambiente": "Local de montagem"},
    {"codigo": "inspecao", "titulo": "Conferência final", "descricao": "Conferir acabamento, folgas e funcionamento de cada unidade.",
     "funcao": None, "entradas": "—", "agentes": "Pessoas da equipe", "ambiente": "Local de montagem"},
]
_POR_CODIGO = {a["codigo"]: a for a in ATIVIDADES}
CODIGOS = tuple(_POR_CODIGO)

ETAPAS = [
    {"codigo": "atividades", "titulo": "Atividades", "rota": "#/preparar/atividades",
     "pergunta": "O que a sua operação faz com o produto, do estoque até o produto pronto?"},
    {"codigo": "entradas", "titulo": "Entradas", "rota": "#/preparar/entradas",
     "pergunta": "O que entra na produção? Informe o produto: peças, material, medidas, pesos e como se ligam."},
    {"codigo": "agentes", "titulo": "Agentes transformadores", "rota": "#/preparar/agentes",
     "pergunta": "Quem e o que transforma as entradas? Pessoas (equipe e horário) e a máquina de cada atividade."},
    {"codigo": "ambiente", "titulo": "Ambiente", "rota": "#/preparar/ambiente",
     "pergunta": "Onde isso acontece? Locais, onde fica cada máquina e a distância entre os locais."},
]


def titulo(codigo: str) -> str:
    return _POR_CODIGO[codigo]["titulo"]


def _tem(atividades: list[str] | None, codigo: str) -> bool:
    return atividades is None or codigo in atividades  # None = tudo (unidades anteriores à trilha)


def _produtos(db: Session, empresa_id: int) -> list[Produto]:
    return list(db.scalars(select(Produto).where(Produto.empresa_id == empresa_id, Produto.ativo.is_(True),
                                                  Produto.tipo == "produto").order_by(Produto.nome)))


def pendencias_produto(db: Session, produto: Produto, atividades: list[str] | None) -> list[str]:
    """O que falta no produto para as atividades escolhidas poderem ser planejadas."""
    comps = list(db.scalars(select(Componente).where(Componente.produto_id == produto.id)))
    if not comps:
        return [f"Informe os componentes de '{produto.nome}'."]
    out: list[str] = []
    paineis = [c for c in comps if c.comprimento_m and c.largura_m]
    if not paineis:
        out.append(f"Informe comprimento e largura (em metros) de ao menos uma peça de '{produto.nome}'.")
    for c in paineis:
        if svc_plano.estimar_peso(c)[0] is None:
            out.append(f"Peso de '{c.nome}': informe o peso, ou o material e a espessura.")
    if _tem(atividades, "montagem") and len(comps) >= 2 and not db.scalar(select(Ligacao.id).where(Ligacao.produto_id == produto.id).limit(1)):
        out.append(f"Diga como as peças de '{produto.nome}' se ligam (método e número de fixadores).")
    for c in comps:
        if (c.furos or 0) > 0 and not _tem(atividades, "furacao"):
            out.append(f"'{c.nome}' tem furos, mas 'Furação' não está nas atividades (etapa 1).")
        if (c.bordas_m or 0) > 0 and not _tem(atividades, "bordo"):
            out.append(f"'{c.nome}' tem borda, mas 'Colagem de borda' não está nas atividades (etapa 1).")
    return out


def _equipamento(recursos: list[Recurso], funcao: str) -> Recurso | None:
    """Mesmo critério do planejador: o que tem capacidade; senão, o primeiro."""
    lista = [r for r in recursos if r.funcao == funcao]
    return next((r for r in lista if r.capacidade), lista[0] if lista else None)


def _etapa_atividades(u: Unidade) -> list[str]:
    return [] if u.atividades else ["Marque as atividades que a sua operação realiza."]


def _etapa_entradas(db: Session, u: Unidade) -> tuple[list[str], dict[int, list[str]]]:
    produtos = _produtos(db, u.empresa_id)
    por_produto = {p.id: pendencias_produto(db, p, u.atividades) for p in produtos}
    if not produtos:
        return ["Cadastre o produto que você fabrica."], por_produto
    if any(not p for p in por_produto.values()):
        return [], por_produto
    melhor = min(produtos, key=lambda p: len(por_produto[p.id]))
    return por_produto[melhor.id], por_produto


def _etapa_agentes(db: Session, u: Unidade, recursos: list[Recurso]) -> list[str]:
    out: list[str] = []
    if not u.equipe_pessoas:
        out.append("Informe quantas pessoas trabalham nesta operação.")
    if not u.jornada or not u.jornada.get("blocos"):
        out.append("Informe o horário de trabalho da equipe.")
    for a in ATIVIDADES:
        if a["funcao"] is None or not _tem(u.atividades, a["codigo"]):
            continue
        eq = _equipamento(recursos, a["funcao"])
        if eq is None:
            out.append(f"Cadastre a máquina que faz {a['titulo'].lower()}.")
        elif not eq.capacidade:
            out.append(f"Informe quantas peças por hora faz '{eq.nome}'.")
    return out


def _etapa_ambiente(db: Session, u: Unidade, recursos: list[Recurso]) -> list[str]:
    espacos = list(db.scalars(select(Espaco).where(Espaco.unidade_id == u.id, Espaco.ativo.is_(True))))

    def local(tipo: str, palavra: str):
        return next((e for e in espacos if e.tipo == tipo), None) or next((e for e in espacos if palavra in e.nome.lower()), None)

    out: list[str] = []
    if _tem(u.atividades, "movimentacao") and not local("estoque", "estoque"):
        out.append("Cadastre o local de estoque (onde as peças ficam antes de cortar).")
    if (_tem(u.atividades, "montagem") or _tem(u.atividades, "inspecao")) and not local("montagem", "montag"):
        out.append("Cadastre o local de montagem.")
    for a in ATIVIDADES:
        if a["funcao"] is None or not _tem(u.atividades, a["codigo"]):
            continue
        eq = _equipamento(recursos, a["funcao"])
        if eq is not None and eq.espaco_id is None:
            out.append(f"Diga em que local fica '{eq.nome}'.")
    if _tem(u.atividades, "movimentacao"):
        for d in contorno.resumo(db, u.empresa_id, [u.id])["distancias"]:
            if d["metros"] is None:
                out.append(f"Informe a distância entre {d['origem']} e {d['destino']} (em metros).")
    return out


def _proximo_apos_trilha(db: Session, u: Unidade) -> dict | None:
    """Com a trilha completa, o próximo passo é o plano e a ordem (o que estiver mais atrasado no caminho)."""
    planos = list(db.scalars(select(PlanoTrabalho).where(PlanoTrabalho.unidade_id == u.id, PlanoTrabalho.status != "cancelado")
                             .order_by(PlanoTrabalho.id.desc()).limit(20)))
    rascunho = next((p for p in planos if p.status == "rascunho"), None)
    if rascunho:
        return {"codigo": "plano_conferir", "titulo": f"Conferir e confirmar o plano “{rascunho.nome}”", "link": f"#/planos/{rascunho.id}", "botao": "Conferir"}
    sem_ordem = next((p for p in planos if p.status == "confirmado" and not p.ordem_id), None)
    if sem_ordem:
        return {"codigo": "gerar_ordem", "titulo": f"Gerar a ordem de produção do plano “{sem_ordem.nome}”", "link": f"#/planos/{sem_ordem.id}", "botao": "Gerar ordem"}
    ordem = db.scalar(select(Ordem).where(Ordem.unidade_id == u.id, Ordem.status == "planejada").order_by(Ordem.id.desc()).limit(1))
    if ordem:
        return {"codigo": "liberar_ordem", "titulo": f"Liberar a ordem {ordem.numero} para a produção", "link": f"#/ordens/{ordem.id}", "botao": "Liberar"}
    if db.scalar(select(Ordem.id).where(Ordem.unidade_id == u.id, Ordem.status.in_(("liberada", "em_producao", "parada"))).limit(1)):
        return None  # produzindo: o resto do Início já mostra alertas e a fila
    return {"codigo": "novo_plano", "titulo": "Planejar a próxima produção", "link": "#/planos", "botao": "Novo plano"}


def calcular(db: Session, u: Unidade) -> dict:
    recursos = list(db.scalars(select(Recurso).where(Recurso.empresa_id == u.empresa_id, Recurso.unidade_id == u.id, Recurso.ativo.is_(True))))
    pend_entradas, por_produto = _etapa_entradas(db, u)
    pendencias = {"atividades": _etapa_atividades(u), "entradas": pend_entradas,
                  "agentes": _etapa_agentes(db, u, recursos), "ambiente": _etapa_ambiente(db, u, recursos)}
    passos, bloqueado, atual = [], False, None
    for i, e in enumerate(ETAPAS, 1):
        pend = pendencias[e["codigo"]]
        estado = "bloqueado" if bloqueado else ("atual" if pend else "concluido")
        if pend and not bloqueado:
            atual = {**e, "numero": i}
        bloqueado = bloqueado or bool(pend)
        passos.append({**e, "numero": i, "estado": estado, "completo": not pend, "pendencias": pend})
    completo = atual is None
    if atual:
        proximo = {"codigo": f"etapa_{atual['codigo']}", "titulo": f"Etapa {atual['numero']} — {atual['titulo']}: {atual['pergunta']}",
                   "link": atual["rota"], "botao": "Continuar"}
    else:
        proximo = _proximo_apos_trilha(db, u)
    return {"unidade_id": u.id, "completo": completo, "passos": passos, "proximo": proximo, "atividades": u.atividades,
            "equipe_pessoas": u.equipe_pessoas, "jornada": u.jornada, "catalogo": ATIVIDADES,
            "pendencias_produto": {str(k): v for k, v in por_produto.items()}}
