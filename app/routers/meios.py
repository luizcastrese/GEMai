"""Cadastro assistido de meios (máquinas, ferramentas, postos, meios de movimentação).

Fluxo: o usuário descreve o meio (nome/modelo, frase ou foto) → a IA identifica (pergunta só se ambíguo) → o usuário
CONFIRMA marca/modelo → a IA busca a ficha técnica na web e o sistema filtra (catálogo, unidade, faixa, fonte) →
os parâmetros aceitos ficam PENDENTES até uma pessoa validar. Só parâmetro validado entra no cálculo.
Sem IA externa: preenchimento manual (rotulado "informado"). O conteúdo da web é dado não confiável: guarda-se só
número + URL de referência.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..config import get_settings
from ..deps import Ctx, get_ctx
from ..models import Parametro, Recurso
from ..ratelimit import limite_ia
from ..schemas import (BuscarFichaIn, BuscarFichaOut, FichaMeioOut, IdentificarMeioIn, IdentificarMeioOut, ParametroOut)
from ..services import ia, imagem
from ..services.ia.esquemas import FichaTecnicaIA, sanear_ficha
from ..services.modulos import ficha as catalogo_ficha
from .processos import _nova_versao_parametro

router = APIRouter(tags=["meios"])


@router.post("/meios/identificar", response_model=IdentificarMeioOut)
def identificar(dados: IdentificarMeioIn, ctx: Ctx = Depends(get_ctx)):
    """Identifica o meio pelo texto (e foto opcional). Devolve candidatos; NADA é gravado: o usuário confirma depois."""
    ctx.exige_unidade(dados.unidade_id)
    limite_ia.checar(f"{ctx.empresa_id}")
    foto = None
    if dados.foto_base64:
        if not ia.externa_disponivel(ctx.empresa):
            raise HTTPException(409, "A foto só é analisada com IA externa habilitada para a empresa. Descreva o meio por texto.")
        try:
            foto = imagem.sanitizar(dados.foto_base64, get_settings().foto_max_bytes)
        except imagem.FotoInvalida as e:
            raise HTTPException(422, f"Foto inválida: {e}.")
    r, prov, aviso = ia.identificar_meio(ctx.empresa, {"texto": dados.texto, "segmento": ctx.empresa.segmento}, foto)
    foto = None  # descartada: nunca gravada nem registrada
    ctx.auditar("meio.identificar", "recurso", None, None, {"provedor": prov, "candidatos": len(r.candidatos), "com_foto": bool(dados.foto_base64)})
    ctx.db.commit()
    return IdentificarMeioOut(candidatos=[c.model_dump() for c in r.candidatos], pergunta=r.pergunta, provedor=prov, aviso=aviso,
                              confirmacao_necessaria=True)


def _estado_da_ficha(ctx: Ctx, r: Recurso) -> FichaMeioOut:
    params = list(ctx.db.scalars(select(Parametro).where(
        Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == "recurso", Parametro.escopo_id == r.id,
        (Parametro.vigente.is_(True)) | (Parametro.status_validacao == "pendente")).order_by(Parametro.nome, Parametro.versao.desc())))
    linhas, pendencias = [], []
    for c in catalogo_ficha.aplicaveis(r.funcao):
        vigente = next((p for p in params if p.nome == c.nome and p.vigente and p.status_validacao == "validado"), None)
        sugestao = next((p for p in params if p.nome == c.nome and p.status_validacao == "pendente"), None)
        linhas.append({"nome": c.nome, "unidade": c.unidade, "descricao": c.descricao, "minimo": c.minimo, "maximo": c.maximo,
                       "vigente": ParametroOut.model_validate(vigente) if vigente else None,
                       "sugestao_pendente": ParametroOut.model_validate(sugestao) if sugestao else None})
        if vigente is None:
            pendencias.append(f"{c.descricao} ({c.nome}): " + ("validar a sugestão encontrada" if sugestao else "informar ou buscar na ficha técnica"))
    if not r.funcao:
        pendencias.insert(0, "Escolha para que serve o meio (função) para ver os parâmetros que ele precisa.")
    return FichaMeioOut(recurso_id=r.id, nome=r.nome, marca=r.marca, modelo=r.modelo, modelo_confirmado=r.modelo_confirmado, funcao=r.funcao,
                        parametros=linhas, pendencias=pendencias, busca_disponivel=ia.externa_disponivel(ctx.empresa))


@router.get("/recursos/{rid}/ficha-tecnica", response_model=FichaMeioOut)
def ver_ficha(rid: int, ctx: Ctx = Depends(get_ctx)):
    return _estado_da_ficha(ctx, ctx.obter(Recurso, rid))


@router.post("/recursos/{rid}/ficha-tecnica/buscar", response_model=BuscarFichaOut)
def buscar_ficha(rid: int, dados: BuscarFichaIn, ctx: Ctx = Depends(get_ctx)):
    """Busca a ficha técnica do modelo CONFIRMADO. Os parâmetros aceitos nascem pendentes (origem `ia_web`) com URL e data."""
    r = ctx.obter(Recurso, rid)
    if not r.modelo_confirmado or not (r.marca or r.modelo):
        raise HTTPException(409, "Confirme marca e modelo do meio antes de buscar a ficha técnica.")
    if not ia.externa_disponivel(ctx.empresa):
        raise HTTPException(409, "A busca de ficha técnica exige IA externa habilitada para a empresa. Preencha os parâmetros manualmente.")
    limite_ia.checar(f"{ctx.empresa_id}")
    catalogo = [{"nome": c.nome, "unidade": c.unidade, "descricao": c.descricao} for c in catalogo_ficha.aplicaveis(r.funcao)]
    ficha, prov, aviso = ia.buscar_ficha(ctx.empresa, {"marca": r.marca, "modelo": r.modelo, "funcao": r.funcao, "catalogo": catalogo})
    aceitos, descartados = sanear_ficha(ficha if isinstance(ficha, FichaTecnicaIA) else FichaTecnicaIA(), r.funcao)
    criados = []
    for a in aceitos:
        # sugestões pendentes anteriores do mesmo parâmetro saem de cena (rejeitadas); a vigente validada não é tocada
        for ant in ctx.db.scalars(select(Parametro).where(
                Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == "recurso", Parametro.escopo_id == r.id,
                Parametro.nome == a["nome"], Parametro.status_validacao == "pendente", Parametro.origem == "ia_web")):
            ant.status_validacao = "rejeitado"
        p = _nova_versao_parametro(
            ctx, r.unidade_id,
            {"escopo_tipo": "recurso", "escopo_id": r.id, "nome": a["nome"], "valor_num": a["valor"], "valor_texto": None,
             "unidade": a["unidade"], "justificativa": f"Ficha técnica encontrada por busca na web para {r.marca} {r.modelo}: confira a fonte antes de validar.".strip(),
             "fonte_url": a["fonte_url"], "fonte_data": date.today(), "confianca": a["confianca"]},
            origem="ia_web", status="pendente", vigente=False)
        criados.append(p)
    pend = []
    if not ficha.encontrada or not aceitos:
        pend.append("A busca não trouxe parâmetros utilizáveis: preencha a ficha técnica manualmente (origem 'informado').")
    ctx.auditar("ficha_tecnica.buscar", "recurso", r.id, None,
                {"provedor": prov, "aceitos": [a["nome"] for a in aceitos], "descartados": len(descartados)})
    ctx.db.commit()
    return BuscarFichaOut(encontrada=bool(aceitos), sugeridos=[ParametroOut.model_validate(p) for p in criados], descartados=descartados,
                          pendencias=pend, provedor=prov, aviso=aviso)
