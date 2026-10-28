"""Plano de trabalho: do produto (componentes + ligações) a passos com tempos e horários.

Fluxo: componentes/ligações + contorno físico → a IA (ou o provedor local) ESCOLHE MÓDULOS do catálogo e mapeia
componentes, equipamentos e locais → o SISTEMA deriva as condições (medidas, pesos, distâncias, ficha técnica dos meios)
e calcula o tempo de cada passo (módulos de vocabulário fechado, ritmo, tolerâncias) → agenda na jornada (intervalos,
dias úteis) e verifica limites. Ninguém digita tempo e a IA não escreve tempos: o que faltar vira "dados faltantes"
e o passo fica sem tempo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from .. import audit
from ..deps import Ctx
from ..models import (Componente, Distancia, Espaco, Ligacao, Ordem, OrdemOperacao, PerfilMaoDeObra, PlanoPasso,
                      PlanoTrabalho, Produto, Recurso)
from . import calibracao_modulos, ergonomia, ia, modelo_tempo
from .modulos import catalogo, entradas, motor
from .dashboard import tz_empresa
from .prontidao import _alerta_simples

BLOCOS_PADRAO = [["08:00", "12:00"], ["13:00", "17:00"]]
ROTULO_TIPO = {"movimentacao": "Transporte", "corte": "Corte", "furacao": "Furação", "bordo": "Borda", "montagem": "Montagem",
               "inspecao": "Conferência", "outro": "Outros"}
LIMITE_JORNADA_MIN = 8 * 60  # CLT art. 58 (jornada normal de 8 h/dia). Conferir com o jurídico/SESMT.


# ------------------------------------------------------------------ entradas
def estimar_peso(c: Componente) -> tuple[float | None, str | None]:
    if c.peso_kg is not None:
        return c.peso_kg, "informado"
    dens = modelo_tempo.DENSIDADES_REFERENCIA.get((c.material or "").lower().strip())
    if dens and c.comprimento_m and c.largura_m and c.espessura_m:
        return round(c.comprimento_m * c.largura_m * c.espessura_m * dens, 3), "estimado"
    return None, None


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _blocos(cfg: dict) -> list[tuple[time, time]]:
    bl = [(_hhmm(a), _hhmm(b)) for a, b in (cfg.get("blocos") or BLOCOS_PADRAO)]
    bl.sort()
    for (a1, b1), (a2, b2) in zip(bl, bl[1:]):
        if b1 > a2:
            raise HTTPException(422, "Os blocos da jornada não podem se sobrepor.")
    if any(b <= a for a, b in bl):
        raise HTTPException(422, "Cada bloco da jornada deve terminar depois de começar.")
    return bl


# ------------------------------------------------------------------ agenda
def _minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def _inicio_util(dt: datetime, blocos, uteis: bool) -> datetime:
    """Primeiro instante de trabalho em ou depois de `dt` (local, sem fuso)."""
    for _ in range(14):
        if uteis and dt.weekday() >= 5:
            dt = datetime.combine(dt.date() + timedelta(days=1), time(0, 0))
            continue
        for a, b in blocos:
            ini, fim = datetime.combine(dt.date(), a), datetime.combine(dt.date(), b)
            if dt < fim:
                return max(dt, ini)
        dt = datetime.combine(dt.date() + timedelta(days=1), time(0, 0))
    raise HTTPException(422, "Não foi possível agendar com a jornada informada.")


def _trabalhado_no_dia(dt: datetime, blocos) -> float:
    total = 0.0
    for a, b in blocos:
        ini, fim = datetime.combine(dt.date(), a), datetime.combine(dt.date(), b)
        if dt > ini:
            total += (min(dt, fim) - ini).total_seconds() / 60
    return total


def agendar(inicio: datetime, blocos, uteis: bool, duracoes: list[float | None]):
    """[(inicio, fim, duracao_efetiva_min | None)] por passo. Passo sem duração não avança o relógio.
    Não há fadiga acumulada digitada: a fadiga por turno só entrará no cálculo quando for aprendida dos dados."""
    cursor = _inicio_util(inicio, blocos, uteis)
    saida = []
    for d in duracoes:
        if d is None:
            saida.append((cursor, cursor, None))
            continue
        inicio_passo = cursor
        efetiva = d
        restante, t = efetiva, inicio_passo
        while restante > 1e-9:
            t = _inicio_util(t, blocos, uteis)
            fim_bloco = next(datetime.combine(t.date(), b) for a, b in blocos if t < datetime.combine(t.date(), b))
            uso = min(restante, (fim_bloco - t).total_seconds() / 60)
            t += timedelta(minutes=uso)
            restante -= uso
        cursor = t
        saida.append((inicio_passo, t, efetiva))
    return saida


def instante_apos(inicio: datetime, blocos, uteis: bool, minutos: float) -> datetime:
    """Instante (local) em que terminam `minutos` de trabalho contados a partir de `inicio`, respeitando blocos e dias úteis."""
    t = _inicio_util(inicio, blocos, uteis)
    restante = minutos
    while restante > 1e-9:
        t = _inicio_util(t, blocos, uteis)
        fim_bloco = next(datetime.combine(t.date(), b) for a, b in blocos if t < datetime.combine(t.date(), b))
        uso = min(restante, (fim_bloco - t).total_seconds() / 60)
        t += timedelta(minutes=uso)
        restante -= uso
    return t


def alertas_jornada(blocos) -> list[dict]:
    liquido = sum(_minutos(b) - _minutos(a) for a, b in blocos)
    folgas = [_minutos(a2) - _minutos(b1) for (a1, b1), (a2, b2) in zip(blocos, blocos[1:])]
    out = []
    if liquido > LIMITE_JORNADA_MIN:
        out.append({"msg": f"A jornada informada tem {liquido / 60:g} h por dia, acima de 8 h: o que passar disso exige horas extras dentro do limite legal.",
                    "detalhe": "CLT arts. 58 e 59 (conferir com o jurídico/SESMT).", "categoria": "seguranca"})
    maior = max(folgas) if folgas else 0
    if liquido > 360 and maior < 60:
        out.append({"msg": "Jornada acima de 6 h por dia precisa de intervalo de pelo menos 1 hora.", "detalhe": "CLT art. 71 (conferir).", "categoria": "seguranca"})
    elif liquido > 240 and maior < 15:
        out.append({"msg": "Jornada entre 4 h e 6 h por dia precisa de um intervalo de pelo menos 15 minutos.", "detalhe": "CLT art. 71 (conferir).", "categoria": "seguranca"})
    return out


# ------------------------------------------------------------------ geração
def _carregar(ctx: Ctx, produto: Produto, unidade_id: int):
    comps = list(ctx.db.scalars(select(Componente).where(Componente.produto_id == produto.id).order_by(Componente.ordem, Componente.id)))
    if not comps:
        raise HTTPException(422, "O produto ainda não tem componentes. Informe a lista de componentes primeiro.")
    ligs = list(ctx.db.scalars(select(Ligacao).where(Ligacao.produto_id == produto.id).order_by(Ligacao.ordem, Ligacao.id)))
    recursos = list(ctx.db.scalars(select(Recurso).where(Recurso.empresa_id == ctx.empresa_id, Recurso.unidade_id == unidade_id, Recurso.ativo.is_(True))))
    espacos = list(ctx.db.scalars(select(Espaco).where(Espaco.empresa_id == ctx.empresa_id, Espaco.unidade_id == unidade_id, Espaco.ativo.is_(True))))
    return comps, ligs, recursos, espacos


@dataclass
class Base:
    """Entradas do plano já carregadas e validadas (preparadas uma vez; reaproveitadas ao avaliar vários arranjos)."""

    ctx: Ctx
    produto: Produto
    unidade_id: int
    cfg: dict
    comps_d: list[dict]
    ligs_d: list[dict]
    esp_id: dict
    esp_nome: dict
    rec_nome: dict
    recursos: list
    fichas: dict
    perfil: PerfilMaoDeObra | None
    ritmo: float
    blocos: list
    pessoas_cfg: int
    pesos: dict
    distancias: list[dict]
    espacos: list


def preparar(ctx: Ctx, produto: Produto, unidade_id: int, cfg: dict) -> Base:
    db = ctx.db
    comps, ligs, recursos, espacos = _carregar(ctx, produto, unidade_id)
    por_id = {c.id: c for c in comps}
    esp_id = {e.id: e for e in espacos}
    perfil = db.get(PerfilMaoDeObra, cfg["perfil_id"]) if cfg.get("perfil_id") else None
    if perfil is not None and (perfil.empresa_id != ctx.empresa_id or perfil.unidade_id != unidade_id):
        raise HTTPException(422, "Perfil de mão de obra inválido para esta unidade.")
    pesos = {c.nome: estimar_peso(c) for c in comps}
    dist_rows = db.scalars(select(Distancia).where(Distancia.empresa_id == ctx.empresa_id, Distancia.unidade_id == unidade_id))
    return Base(
        ctx=ctx, produto=produto, unidade_id=unidade_id, cfg=cfg, comps_d=[entradas.componente_dict(c, pesos[c.nome][0]) for c in comps],
        ligs_d=[{"componente": por_id[l.componente_id].nome, "ligado_a": por_id[l.ligado_a_id].nome if l.ligado_a_id in por_id else None,
                 "metodo": l.metodo, "fixadores": l.fixadores} for l in ligs if l.componente_id in por_id],
        esp_id=esp_id, esp_nome={e.nome.lower(): e for e in espacos}, rec_nome={r.nome.lower(): r for r in recursos}, recursos=recursos,
        fichas={r.id: entradas.ficha_do_meio(db, ctx.empresa_id, r.id) for r in recursos}, perfil=perfil,
        ritmo=perfil.ritmo_pct if perfil else 100.0, blocos=_blocos(cfg), pessoas_cfg=max(int(cfg.get("pessoas") or 1), 1), pesos=pesos,
        distancias=[{"a": esp_id[d.origem_id].nome, "b": esp_id[d.destino_id].nome, "metros": d.metros}
                    for d in dist_rows if d.origem_id in esp_id and d.destino_id in esp_id], espacos=espacos)


def propor(base: Base, quantidade: float):
    """A IA (ou o provedor local) ESCOLHE módulos e mapeia componentes/equipamentos/locais. Contexto enviado: nomes, medidas e
    pesos do produto; nenhum tempo, taxa ou coeficiente."""
    ctx = base.ctx
    contexto = {
        "segmento": ctx.empresa.segmento,
        "produto": {"nome": base.produto.nome, "quantidade": quantidade},
        "componentes": [{"nome": c["nome"], "qtd": c["qtd"], "material": c["material"], "grupo": c["grupo"], "comp": c["comp"],
                         "larg": c["larg"], "esp": c["esp"], "peso_kg": c["peso_kg"], "peso_origem": base.pesos[c["nome"]][1],
                         "furos": c["furos"], "bordas_m": c["bordas_m"]} for c in base.comps_d],
        "ligacoes": base.ligs_d,
        "recursos": [{"nome": r.nome, "funcao": r.funcao, "tipo": r.tipo, "ficha_tecnica": sorted(base.fichas[r.id]),
                      "espaco": base.esp_id[r.espaco_id].nome if r.espaco_id in base.esp_id else None} for r in base.recursos],
        "espacos": [{"nome": e.nome, "tipo": e.tipo, "temperatura_c": e.temperatura_c, "ruido_db": e.ruido_db} for e in base.espacos],
        "distancias": base.distancias, "pessoas": base.pessoas_cfg, "modulos": catalogo.resumo_para_ia(),
    }
    return ia.planejar(ctx.empresa, contexto)


def calcular_linha(base: Base, p, quantidade: float, *, recurso=None, pessoas_cfg: int | None = None, fixar_recurso: bool = False) -> dict:
    """Calcula UM passo (módulo + condições) para `quantidade` unidades do produto. `recurso` troca o equipamento/meio
    proposto (usado ao avaliar arranjos; com `fixar_recurso`, `recurso=None` significa "sem meio", não "o proposto"); `pessoas_cfg` troca o
    mínimo de pessoas do passo."""
    ctx, db = base.ctx, base.ctx.db
    modulo = catalogo.obter(p.modulo)
    rec = recurso if (recurso is not None or fixar_recurso) else base.rec_nome.get((p.recurso or "").lower())
    o, d = base.esp_nome.get((p.espaco_origem or "").lower()), base.esp_nome.get((p.espaco_destino or "").lower())
    distancia = None
    if o and d:
        distancia = 0.0 if o.id == d.id else modelo_tempo.distancia_entre(db, ctx.empresa_id, o.id, d.id)
    pessoas = max(p.pessoas, pessoas_cfg if pessoas_cfg is not None else base.pessoas_cfg)
    ent = entradas.entrada_do_passo(modulo, p, comps=base.comps_d, ligs=base.ligs_d, unidades_produto=quantidade, pessoas=pessoas,
                                    distancia_m=distancia, rec=rec, ficha=base.fichas.get(rec.id, {}) if rec else {},
                                    origem=o.nome if o else None, destino=d.nome if d else None)
    local = (base.esp_id.get(rec.espaco_id) if rec else None) or d or o
    tol = motor.tolerancias_padrao()  # sem "folga extra" digitada: o ambiente será calculado (Fase 8)
    cal = calibracao_modulos.fator_vigente(db, ctx.empresa_id, base.unidade_id, modulo.chave)  # só calibração VALIDADA
    r = motor.calcular_modulo(modulo, ent, tolerancias=tol, ritmo_pct=base.ritmo, calibracao=calibracao_modulos.como_dict(cal))
    pessoas = r.pessoas
    falt = list(r.faltantes)
    if modulo.precisa_recurso and rec is None and not any("equipamento" in f for f in falt):
        falt.append("falta o equipamento deste passo (cadastre e escolha um meio)")
    alertas = []
    peso_ref = ent.peso_max_kg
    if peso_ref and not (modulo.chave == "movimentacao" and ent.meio_nome):  # com meio, ninguém carrega a peça
        for a in ergonomia.alertas_carga(peso_ref / pessoas, base.perfil, None):
            txt, cat = _alerta_simples(a)
            alertas.append({"msg": txt, "detalhe": a, "categoria": cat})
    for a in r.alertas:
        alertas.append({"msg": a, "detalhe": a, "categoria": "seguranca"})
    if local is not None:
        if local.ruido_db and local.ruido_db > ergonomia.LIMITE_RUIDO_NR15_DBA:
            txt, cat = _alerta_simples(f"Ruído de {local.ruido_db:g} dB(A) em '{local.nome}' acima de {ergonomia.LIMITE_RUIDO_NR15_DBA:g} dB(A) (NR-15, 8 h)")
            alertas.append({"msg": txt, "detalhe": f"Ruído {local.ruido_db:g} dB(A) em '{local.nome}'", "categoria": cat})
        if local.temperatura_c is not None and (local.temperatura_c > 30 or local.temperatura_c < 12):
            alertas.append({"msg": f"A temperatura em '{local.nome}' ({local.temperatura_c:g} °C) é extrema: avalie o conforto térmico e informe a tolerância do local, se couber.",
                            "detalhe": "NR-15/NHO-06 e NR-17: avaliação de calor/frio.", "categoria": "seguranca"})
    completo = not falt
    return {"p": p, "modulo": modulo, "ent": ent, "rec": rec, "o": o, "d": d, "pessoas": pessoas, "tol": tol, "r": r, "falt": falt,
            "alertas": alertas, "total": r.total if completo else None, "prep": r.prep if completo else None,
            "exec": r.exec if completo else None, "normal": r.normal if completo else None,
            "cal_amostras": cal.amostras if (cal and r.calibrado) else 0, "peso_por_pessoa": (peso_ref / pessoas) if peso_ref else None}


def inicio_local_do_plano(ctx: Ctx, cfg: dict) -> datetime:
    tz = tz_empresa(ctx.empresa)
    inicio_cfg = cfg.get("inicio")
    return (inicio_cfg.astimezone(tz).replace(tzinfo=None) if inicio_cfg else datetime.now(timezone.utc).astimezone(tz).replace(tzinfo=None))


def persistir(base: Base, quantidade: float, plano: PlanoTrabalho | None, proposta, provedor: str, aviso: str, linhas: list[dict],
              ag: list, extras_config: dict | None = None, extras_totais: dict | None = None, extras_premissas: list[str] | None = None) -> PlanoTrabalho:
    """Grava o plano: um PlanoPasso por linha (`l["nome"]`, se houver, substitui o nome do passo) com a agenda `ag`
    [(início local, fim local, duração efetiva | None)] alinhada às linhas."""
    ctx, db, cfg, produto, unidade_id = base.ctx, base.ctx.db, base.cfg, base.produto, base.unidade_id
    tz = tz_empresa(ctx.empresa)
    if plano is None:
        plano = PlanoTrabalho(empresa_id=ctx.empresa_id, unidade_id=unidade_id, produto_id=produto.id, criado_por=ctx.usuario.id,
                              nome=cfg.get("nome") or f"{produto.nome} × {quantidade:g}", quantidade=quantidade)
        db.add(plano)
        db.flush()
    else:
        for passo in list(plano.passos):
            db.delete(passo)
        db.flush()
        plano.quantidade = quantidade
    cfg_guardada = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in cfg.items() if k != "nome"}
    cfg_guardada.update(extras_config or {})
    totais_p = totais_a = hh = 0.0
    incompletos = 0
    for i, (l, (ini, fim, efetiva)) in enumerate(zip(linhas, ag), 1):
        p = l["p"]
        if l["total"] is not None:
            totais_p += l["total"]
            totais_a += efetiva or 0
            hh += l["total"] * l["pessoas"] / 60
        else:
            incompletos += 1
        mod, r = l["modulo"], l["r"]
        db.add(PlanoPasso(
            empresa_id=ctx.empresa_id, plano_id=plano.id, sequencia=i, nome=l.get("nome", p.nome), tipo=mod.tipo_passo, grupo=p.grupo, componentes=p.componentes,
            qtd_pecas=l["ent"].quantidade, recurso_id=l["rec"].id if l["rec"] else None, espaco_origem_id=l["o"].id if l["o"] else None,
            espaco_destino_id=l["d"].id if l["d"] else None, pessoas=l["pessoas"], elementos=r.elementos,
            tolerancias=l["tol"], ritmo_pct=base.ritmo, composicao=r.composicao, tempo_prep_min=l["prep"], tempo_exec_min=l["exec"],
            tempo_padrao_min=l["total"], tempo_normal_min=l["normal"], tempo_agendado_min=round(efetiva, 3) if efetiva is not None else None,
            faltantes=l["falt"], alertas=l["alertas"], observacao=p.observacao, modulo=mod.chave, modulo_versao=mod.versao,
            parametros_modulo=r.parametros, coeficientes=r.coeficientes, previsto_normal_min=r.normal_base if l["total"] is not None else None,
            fracao_operador=r.fracao_operador, fator_calibracao=r.fator_calibracao, amostras_calibracao=l["cal_amostras"],
            inicio_prev=ini.replace(tzinfo=tz).astimezone(timezone.utc) if l["total"] is not None else None,
            fim_prev=fim.replace(tzinfo=tz).astimezone(timezone.utc) if l["total"] is not None else None))
    fim_geral = max((f for (_, f, e) in ag if e is not None), default=None)
    inicio_geral = min((i for (i, _, e) in ag if e is not None), default=None)
    dias = len({f.date() for (_, f, e) in ag if e is not None} | {i.date() for (i, _, e) in ag if e is not None})
    faltantes = list(dict.fromkeys(proposta.dados_faltantes + [f"{l['p'].nome}: {x}" for l in linhas for x in l["falt"]]))
    plano.config = cfg_guardada
    # sem histórico medido do plano, nunca "alta": a confiança da IA é só um rótulo, o sistema limita
    plano.provedor, plano.confianca = provedor, ("baixa" if (incompletos or proposta.confianca == "baixa") else "media")
    obsoleto = ["O campo 'fadiga % por hora' é obsoleto e foi ignorado: a fadiga por turno só entra no cálculo quando for aprendida dos dados."] \
        if cfg.get("fadiga_ignorada") else []
    plano.premissas = list(dict.fromkeys(proposta.premissas + [x for l in linhas for x in l["r"].premissas] + premissas_coeficientes(linhas)
                                         + obsoleto + (extras_premissas or []) + ([aviso] if aviso else [])))
    plano.faltantes = faltantes
    plano.alertas = alertas_jornada(base.blocos)
    plano.totais = {"passos": len(linhas), "passos_incompletos": incompletos, "tempo_padrao_min": round(totais_p, 2),
                    "tempo_agendado_min": round(totais_a, 2), "horas_homem": round(hh, 2), "dias": dias,
                    "inicio": (inicio_geral.replace(tzinfo=tz).astimezone(timezone.utc).isoformat() if inicio_geral else None),
                    "fim": (fim_geral.replace(tzinfo=tz).astimezone(timezone.utc).isoformat() if fim_geral else None),
                    "completo": incompletos == 0 and not proposta.dados_faltantes, **(extras_totais or {})}
    plano.status = "rascunho"
    plano.confirmado_por = plano.confirmado_em = None
    db.flush()
    return plano


def gerar(ctx: Ctx, produto: Produto, quantidade: float, unidade_id: int, cfg: dict, plano: PlanoTrabalho | None = None) -> PlanoTrabalho:
    """Plano SEQUENCIAL (uma equipe, um passo por vez). Para paralelismo, lotes e meios veja `services/arranjo`."""
    base = preparar(ctx, produto, unidade_id, cfg)
    proposta, provedor, aviso = propor(base, quantidade)
    linhas = [calcular_linha(base, p, quantidade) for p in proposta.passos]
    ag = agendar(inicio_local_do_plano(ctx, cfg), base.blocos, cfg.get("so_dias_uteis", True), [l["total"] for l in linhas])
    return persistir(base, quantidade, plano, proposta, provedor, aviso, linhas, ag)


def premissas_coeficientes(linhas: list[dict]) -> list[str]:
    """Declara os coeficientes usados (valor, fonte e status), sem repetir: genéricos de referência e calibrações validadas."""
    vistos: dict[str, dict] = {}
    for l in linhas:
        for c in l["r"].coeficientes:
            vistos.setdefault(c["chave"], c)
    gen = [c for c in vistos.values() if c["status"] == "referencia_generica"]
    cal = [c for c in vistos.values() if c["status"] == "calibrado"]
    out = []
    if gen:
        out.append("Coeficientes de referência genéricos do catálogo (confiança baixa, a calibrar com o seu histórico): " +
                   "; ".join(f"{c['chave']} = {c['valor']:g} {c['unidade']}" for c in sorted(gen, key=lambda c: c["chave"])) + ".")
    if cal:
        out.append("Módulos CALIBRADOS com o seu histórico (calibração validada por uma pessoa): " +
                   "; ".join(f"{c['chave'].split(':')[1]} × {c['valor']:g} ({c['fonte']})" for c in sorted(cal, key=lambda c: c["chave"])) + ".")
    return out


def hierarquia_do_plano(produto_nome: str, plano: PlanoTrabalho) -> dict:
    """produto → grupo → módulo → elementos, com tempo normal, tolerâncias, padrão e preparação separada."""
    passos = [{"grupo": p.grupo or ROTULO_TIPO.get(p.tipo, "Outros"), "modulo": p.modulo, "titulo": (catalogo.obter(p.modulo).titulo if catalogo.obter(p.modulo) else p.tipo),
               "nome": p.nome, "pessoas": p.pessoas, "composicao": p.composicao, "tempo_normal_min": p.tempo_normal_min,
               "tempo_prep_min": p.tempo_prep_min, "tempo_exec_min": p.tempo_exec_min, "tempo_padrao_min": p.tempo_padrao_min,
               "faltantes": p.faltantes} for p in plano.passos]
    return motor.hierarquia(produto_nome, plano.quantidade, passos)


# ------------------------------------------------------------------ plano → ordem de produção
def gerar_ordem(ctx: Ctx, plano: PlanoTrabalho, cliente: str, prazo, numero_fn) -> Ordem:
    if plano.status != "confirmado":
        raise HTTPException(409, "Confirme o plano antes de gerar a ordem de produção.")
    if plano.ordem_id:
        raise HTTPException(409, "Este plano já gerou uma ordem.")
    produto = ctx.db.get(Produto, plano.produto_id)
    tem_tempo = [p for p in plano.passos if p.tempo_padrao_min is not None]
    o = Ordem(empresa_id=ctx.empresa_id, unidade_id=plano.unidade_id, numero=numero_fn(ctx.db, ctx.empresa_id), cliente=cliente,
              produto_id=plano.produto_id, descricao=produto.nome if produto else plano.nome, quantidade=plano.quantidade, prazo=prazo,
              processo_id=None, plano_id=plano.id, status="planejada", criada_por=ctx.usuario.id,
              tempo_estimado_min=round(sum(p.tempo_padrao_min for p in tem_tempo), 2) if tem_tempo else None,
              observacoes=f"Gerada do plano de trabalho #{plano.id}.")
    ctx.db.add(o)
    ctx.db.flush()
    for p in plano.passos:
        ok = p.tempo_padrao_min is not None
        ctx.db.add(OrdemOperacao(
            empresa_id=ctx.empresa_id, ordem_id=o.id, operacao_id=None, sequencia=p.sequencia, etapa_nome=p.grupo or ROTULO_TIPO.get(p.tipo, "Outros"), nome=p.nome,
            recurso_id=p.recurso_id, qtd_planejada=p.qtd_pecas, formula_tipo="fixo", tempo_prep_est_min=p.tempo_prep_min if ok else None,
            tempo_exec_est_min=p.tempo_exec_min if ok else None, fonte_estimativa="plano" if ok else "sem_base", amostras=0,
            detalhe_estimativa=p.composicao, estimativa_validada=True, status="pendente",
            plano_passo_id=p.id, modulo=p.modulo or None, previsto_normal_min=p.previsto_normal_min if ok else None,
            fracao_operador=p.fracao_operador, fator_calibracao=p.fator_calibracao or 1.0))
    plano.ordem_id = o.id
    ctx.db.flush()
    ctx.db.refresh(o)
    return o
