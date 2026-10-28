"""Primeiros passos: o caminho do produto até a primeira ordem, em linguagem comum.

Produto → Sua oficina → Plano → Confirmar → Produzir. Cada passo diz se já foi feito e para onde ir;
o primeiro que falta é o "atual". Nada é gravado: tudo é deduzido do que a empresa já cadastrou.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Componente, Espaco, PlanoTrabalho, Produto


def passos(db: Session, empresa_id: int, unidade_ids: list[int]) -> dict:
    produtos = list(db.scalars(select(Produto).where(
        Produto.empresa_id == empresa_id, Produto.ativo.is_(True), Produto.tipo == "produto").order_by(Produto.id.desc())))
    com_componentes = set(db.scalars(select(Componente.produto_id).where(
        Componente.empresa_id == empresa_id, Componente.produto_id.in_([p.id for p in produtos] or [0]))))
    sem_componentes = next((p for p in produtos if p.id not in com_componentes), None)
    locais = db.scalar(select(func.count(Espaco.id)).where(
        Espaco.empresa_id == empresa_id, Espaco.unidade_id.in_(unidade_ids or [0]), Espaco.ativo.is_(True))) or 0
    planos = list(db.scalars(select(PlanoTrabalho).where(
        PlanoTrabalho.empresa_id == empresa_id, PlanoTrabalho.unidade_id.in_(unidade_ids or [0]),
        PlanoTrabalho.status != "cancelado").order_by(PlanoTrabalho.id)))
    rascunho = next((p for p in planos if p.status == "rascunho"), None)
    sem_ordem = next((p for p in planos if p.status == "confirmado" and not p.ordem_id), None)

    lista = [
        {"codigo": "produto", "rotulo": "Produto", "titulo": "Cadastre o que você fabrica",
         "explicacao": "Diga do que o produto é feito (as peças) e como elas se juntam. Pode escrever com suas palavras que a IA monta a lista.",
         "feito": bool(com_componentes),
         "link": f"#/produtos/{sem_componentes.id}" if sem_componentes else "#/produtos",
         "botao": "Continuar o produto" if sem_componentes else "Cadastrar produto"},
        {"codigo": "oficina", "rotulo": "Oficina", "titulo": "Conte como é a sua oficina",
         "explicacao": "Onde ficam o estoque, as máquinas e a montagem, e quantas peças cada máquina faz por hora. É só o essencial.",
         "feito": locais > 0, "link": "#/contorno", "botao": "Contar sobre a oficina"},
        {"codigo": "plano", "rotulo": "Plano", "titulo": "Monte o plano de trabalho",
         "explicacao": "O sistema sugere o passo a passo para fabricar o produto, com o tempo e o horário de cada passo.",
         "feito": bool(planos), "link": "#/planos", "botao": "Montar o plano"},
        {"codigo": "confirmar", "rotulo": "Conferir", "titulo": "Confira e confirme o plano",
         "explicacao": "A sugestão só vale depois que você olhar os passos e apertar “Confirmar plano”.",
         "feito": any(p.status == "confirmado" for p in planos),
         "link": f"#/planos/{rascunho.id}" if rascunho else "#/planos", "botao": "Conferir o plano"},
        {"codigo": "ordem", "rotulo": "Produzir", "titulo": "Comece a produzir",
         "explicacao": "Transforme o plano em uma ordem de produção. Ela vai para a “Minha fila” e a equipe registra o trabalho.",
         "feito": any(p.ordem_id for p in planos),
         "link": f"#/planos/{sem_ordem.id}" if sem_ordem else "#/planos", "botao": "Gerar a ordem de produção"},
    ]
    for i, p in enumerate(lista, 1):
        p["numero"] = i
    atual = next((p["numero"] for p in lista if not p["feito"]), None)
    return {"passos": lista, "atual": atual, "feitos": sum(p["feito"] for p in lista), "total": len(lista)}
