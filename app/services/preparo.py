"""Preparo do item: o que a plataforma deduz do item final e do que ainda falta para calcular o tempo.

A pessoa informa três coisas, numa tela só:
  • o item final e suas peças (componentes, medidas, material, furos, borda e como se ligam);
  • os agentes: pessoas (equipe e horário) e as máquinas;
  • o ambiente: locais, onde fica cada máquina e a distância entre eles.

As ATIVIDADES (transporte, corte, borda, furação, montagem, conferência) não são perguntadas: saem das peças.
Este módulo repete a dedução do planejador para dizer, ANTES de gerar o plano, o que falta em cada seção.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Componente, Espaco, Ligacao, Ordem, PlanoTrabalho, Produto, Recurso, Unidade
from . import contorno, plano as svc_plano

SECOES = [
    {"codigo": "pecas", "titulo": "Item e peças"},
    {"codigo": "agentes", "titulo": "Agentes (pessoas e máquinas)"},
    {"codigo": "ambiente", "titulo": "Ambiente"},
]

# função da máquina que executa cada atividade de usinagem
_MAQUINA = {"corte": "corte", "bordo": "bordo", "furacao": "furacao"}
_TITULO = {"movimentacao": "Transporte interno", "corte": "Corte", "bordo": "Colagem de borda", "furacao": "Furação",
           "montagem": "Montagem", "inspecao": "Conferência final"}


def _comps(db: Session, produto: Produto) -> list[Componente]:
    return list(db.scalars(select(Componente).where(Componente.produto_id == produto.id).order_by(Componente.ordem, Componente.id)))


def atividades_do_item(db: Session, produto: Produto) -> list[dict]:
    """As atividades que o plano terá para este item (mesma regra do planejador)."""
    comps = _comps(db, produto)
    paineis = [c for c in comps if c.comprimento_m and c.largura_m]
    ligs = db.scalar(select(Ligacao.id).where(Ligacao.produto_id == produto.id).limit(1))
    out = []
    if paineis:
        out.append({"codigo": "movimentacao", "pecas": sum(c.quantidade for c in paineis)})
        out.append({"codigo": "corte", "pecas": sum(c.quantidade for c in paineis)})
        if any((c.bordas_m or 0) > 0 for c in paineis):
            out.append({"codigo": "bordo", "pecas": sum(c.quantidade for c in paineis if (c.bordas_m or 0) > 0)})
        if any((c.furos or 0) > 0 for c in paineis):
            out.append({"codigo": "furacao", "pecas": sum(c.quantidade for c in paineis if (c.furos or 0) > 0)})
    if len(comps) >= 2 or ligs:
        out.append({"codigo": "montagem", "pecas": sum(c.quantidade for c in comps)})
    if comps:
        out.append({"codigo": "inspecao", "pecas": None})
    return [{**a, "titulo": _TITULO[a["codigo"]], "funcao": _MAQUINA.get(a["codigo"])} for a in out]


def _equipamento(recursos: list[Recurso], funcao: str) -> Recurso | None:
    """Mesmo critério do planejador: o que tem capacidade; senão, o primeiro."""
    lista = [r for r in recursos if r.funcao == funcao]
    return next((r for r in lista if r.capacidade), lista[0] if lista else None)


def _pend_pecas(db: Session, produto: Produto, atividades: list[dict]) -> list[str]:
    comps = _comps(db, produto)
    if not comps:
        return [f"Informe as peças de '{produto.nome}'."]
    out: list[str] = []
    paineis = [c for c in comps if c.comprimento_m and c.largura_m]
    if not paineis:
        out.append("Informe comprimento e largura (em metros) de ao menos uma peça.")
    for c in paineis:
        if svc_plano.estimar_peso(c)[0] is None:
            out.append(f"Peso de '{c.nome}': informe o peso, ou o material e a espessura.")
    if any(a["codigo"] == "montagem" for a in atividades) and not db.scalar(select(Ligacao.id).where(Ligacao.produto_id == produto.id).limit(1)):
        out.append("Diga como as peças se ligam (método e número de fixadores).")
    return out


_SEM_PECAS = "Informe as peças primeiro: elas definem as atividades, as máquinas e os locais necessários."


def _pend_agentes(atividades: list[dict], recursos: list[Recurso]) -> list[str]:
    if not atividades:
        return [_SEM_PECAS]
    out: list[str] = []
    for a in atividades:
        if not a["funcao"]:
            continue
        eq = _equipamento(recursos, a["funcao"])
        if eq is None:
            out.append(f"Cadastre a máquina que faz {a['titulo'].lower()}.")
        elif not eq.capacidade:
            out.append(f"Informe quantas peças por hora faz '{eq.nome}'.")
    return out


def _pend_ambiente(db: Session, u: Unidade, atividades: list[dict], recursos: list[Recurso]) -> list[str]:
    if not atividades:
        return [_SEM_PECAS]
    espacos = list(db.scalars(select(Espaco).where(Espaco.unidade_id == u.id, Espaco.ativo.is_(True))))

    def local(tipo: str, palavra: str):
        return next((e for e in espacos if e.tipo == tipo), None) or next((e for e in espacos if palavra in e.nome.lower()), None)

    out: list[str] = []
    cods = {a["codigo"] for a in atividades}
    if "movimentacao" in cods and not local("estoque", "estoque"):
        out.append("Cadastre o local de estoque (onde as peças ficam antes de cortar).")
    if cods & {"montagem", "inspecao"} and not local("montagem", "montag"):
        out.append("Cadastre o local de montagem.")
    for a in atividades:
        eq = _equipamento(recursos, a["funcao"]) if a["funcao"] else None
        if eq is not None and eq.espaco_id is None:
            out.append(f"Diga em que local fica '{eq.nome}'.")
    if "movimentacao" in cods:
        for d in contorno.resumo(db, u.empresa_id, [u.id])["distancias"]:
            if d["metros"] is None:
                out.append(f"Informe a distância entre {d['origem']} e {d['destino']} (em metros).")
    return out


def calcular(db: Session, u: Unidade, produto: Produto) -> dict:
    atividades = atividades_do_item(db, produto)
    recursos = list(db.scalars(select(Recurso).where(Recurso.empresa_id == u.empresa_id, Recurso.unidade_id == u.id, Recurso.ativo.is_(True))))
    pend = {"pecas": _pend_pecas(db, produto, atividades), "agentes": _pend_agentes(atividades, recursos),
            "ambiente": _pend_ambiente(db, u, atividades, recursos)}
    secoes = [{**s, "pendencias": pend[s["codigo"]], "completo": not pend[s["codigo"]]} for s in SECOES]
    return {"produto_id": produto.id, "unidade_id": u.id, "atividades": atividades, "secoes": secoes,
            "pendencias_total": sum(len(v) for v in pend.values()), "pode_gerar": bool(_comps(db, produto)),
            "equipe_pessoas": u.equipe_pessoas, "jornada": u.jornada}


def proximo(db: Session, u: Unidade) -> dict | None:
    """O que a pessoa deve fazer a seguir nesta unidade (usado no Início)."""
    produto = db.scalar(select(Produto).where(Produto.empresa_id == u.empresa_id, Produto.ativo.is_(True), Produto.tipo == "produto")
                        .order_by(Produto.id.desc()).limit(1))
    if produto is None:
        return {"codigo": "novo_item", "titulo": "Informe o item que você fabrica (ex.: armário) e as peças que o compõem", "link": "#/itens", "botao": "Começar"}
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
    if not planos:
        return {"codigo": "gerar_plano", "titulo": f"Gerar o plano de trabalho de “{produto.nome}”", "link": f"#/itens/{produto.id}", "botao": "Gerar plano"}
    return {"codigo": "novo_plano", "titulo": "Planejar a próxima produção", "link": "#/itens", "botao": "Novo plano"}
