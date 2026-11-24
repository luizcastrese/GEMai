"""Indicadores do piloto (validação de campo, seção 10.4 do README): calculados SÓ com os dados que o sistema já guarda.

Não há rastreamento de cliques nem dado pessoal: tudo é agregado da empresa. Cada indicador responde a uma questão de pesquisa:
- QP3 (usabilidade): tempo do cadastro ao primeiro plano; planos completos; planos confirmados que viraram pedido;
- QP2 (calibração): erro do previsto contra o realizado por pedido, separando pedidos SEM e COM fator de calibração validado;
- QP4 (generalidade): atividades propostas pela IA validadas sem edição, editadas ou rejeitadas;
- adesão à medição: fração dos pedidos abertos que foram medidos (e como: passo a passo ou no total).

Erro de um pedido = |ln(realizado ÷ previsto)| (simétrico para mais e para menos), resumido pela mediana e convertido em %.
Previsto = tempo padrão da ordem; realizado = tempo corrido apontado (união dos intervalos aprovados, não anulados).
"""
from __future__ import annotations

import math
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Apontamento, CalibracaoModulo, Componente, Empresa, ModuloEmpresa, Ordem, PlanoTrabalho, Produto
from . import timecalc


def _min_entre(a, b) -> float | None:
    return round((b - a).total_seconds() / 60.0, 1) if a and b else None


def _pct(erros: list[float]) -> float | None:
    return round((math.exp(timecalc.mediana(erros)) - 1) * 100, 1) if erros else None


def indicadores(db: Session, empresa_id: int) -> dict:
    emp = db.get(Empresa, empresa_id)
    planos = list(db.scalars(select(PlanoTrabalho).where(PlanoTrabalho.empresa_id == empresa_id).order_by(PlanoTrabalho.criado_em)))
    ordens = list(db.scalars(select(Ordem).where(Ordem.empresa_id == empresa_id, Ordem.plano_id.is_not(None))))
    tem_item = db.scalar(select(Componente.id).where(Componente.empresa_id == empresa_id).limit(1)) is not None
    produtos = db.scalar(select(Produto.id).where(Produto.empresa_id == empresa_id).limit(1)) is not None

    # --- QP2: previsto × realizado por pedido
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_id.in_([o.id for o in ordens] or [-1]), Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    por_ordem: dict[int, list] = {}
    for a in apts:
        por_ordem.setdefault(a.ordem_id, []).append(a)
    pedidos, erros_sem, erros_com = [], [], []
    formas = Counter()
    for o in ordens:
        lista = por_ordem.get(o.id)
        if o.status != "concluida" or not lista or not o.tempo_estimado_min:
            continue
        real = timecalc.uniao_minutos((a.inicio, a.fim) for a in lista)
        if real <= 0:
            continue
        calibrado = any((x.fator_calibracao or 1.0) != 1.0 for x in o.operacoes)
        forma = "total" if any((a.dados_extras or {}).get("origem") == "total_do_pedido" for a in lista) else "passo_a_passo"
        formas[forma] += 1
        erro = abs(math.log(real / o.tempo_estimado_min))
        (erros_com if calibrado else erros_sem).append(erro)
        pedidos.append({"ordem_id": o.id, "previsto_min": round(o.tempo_estimado_min, 2), "realizado_min": round(real, 2),
                        "desvio_pct": round((real / o.tempo_estimado_min - 1) * 100, 1), "calibrado": calibrado, "forma": forma,
                        "concluida_em": o.concluida_em.isoformat() if o.concluida_em else None})

    # --- QP4: atividades delimitadas pela IA
    mods = list(db.scalars(select(ModuloEmpresa).where(ModuloEmpresa.empresa_id == empresa_id).order_by(ModuloEmpresa.chave, ModuloEmpresa.versao)))
    por_chave: dict[str, list] = {}
    for m in mods:
        por_chave.setdefault(m.chave, []).append(m)
    ativ = Counter()
    for versoes in por_chave.values():
        primeira = versoes[0]
        if primeira.origem != "ia":
            ativ["criadas_por_pessoa"] += 1
            continue
        validadas = [v for v in versoes if v.status == "validado"]
        if not validadas:
            ativ["ia_rejeitadas" if all(v.status == "rejeitado" for v in versoes) else "ia_pendentes"] += 1
        elif validadas[0].versao == 1 and validadas[0].espec == primeira.espec:
            ativ["ia_validadas_sem_edicao"] += 1
        else:
            ativ["ia_validadas_com_edicao"] += 1

    cal = Counter(c.status for c in db.scalars(select(CalibracaoModulo).where(CalibracaoModulo.empresa_id == empresa_id)))
    from ..models import Intervencao
    from . import intervencoes as interv
    efeitos = [interv.efeito(db, i) for i in db.scalars(select(Intervencao).where(Intervencao.empresa_id == empresa_id))]
    conclusivos = [e for e in efeitos if e["conclusivo"]]
    primeiro_plano = planos[0].criado_em if planos else None
    abertos = len(ordens)
    medidos = len(pedidos)
    return {
        "empresa": {"segmento": emp.segmento if emp else "", "pacotes": list(emp.pacotes or []) if emp else [],
                    "cadastro_em": emp.criada_em.isoformat() if emp and emp.criada_em else None},
        "uso": {"tem_produto": produtos, "tem_itens": tem_item,
                "minutos_do_cadastro_ao_primeiro_plano": _min_entre(emp.criada_em if emp else None, primeiro_plano),
                "planos": len(planos), "planos_completos": sum(1 for p in planos if (p.totais or {}).get("completo")),
                "planos_confirmados": sum(1 for p in planos if p.status == "confirmado"),
                "planos_com_pedido": sum(1 for p in planos if p.ordem_id)},
        "medicao": {"pedidos_abertos": abertos, "pedidos_medidos": medidos,
                    "fracao_medida": round(medidos / abertos, 3) if abertos else None, "formas": dict(formas)},
        "previsto_x_realizado": {"erro_tipico_sem_calibracao_pct": _pct(erros_sem), "pedidos_sem_calibracao": len(erros_sem),
                                 "erro_tipico_com_calibracao_pct": _pct(erros_com), "pedidos_com_calibracao": len(erros_com),
                                 "pedidos": pedidos},
        "atividades": dict(ativ),
        "calibracoes": dict(cal),
        "intervencoes": {"registradas": len(efeitos), "conclusivas": len(conclusivos),
                         "melhoraram": sum(1 for e in conclusivos if e["variacao_erro_pp"] < 0),
                         "variacao_mediana_erro_pp": round(timecalc.mediana([e["variacao_erro_pp"] for e in conclusivos]), 1) if conclusivos else None},
        "metodo": ("Erro de um pedido = |ln(realizado ÷ previsto)|; erro típico = mediana convertida em %. Previsto = tempo padrão da "
                   "ordem; realizado = tempo corrido apontado e aprovado. 'Com calibração' = pedido cujo plano usou fator validado."),
    }
