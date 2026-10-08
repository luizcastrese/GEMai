"""Prontidão do processo para o gêmeo digital (checagem determinística, sem IA).

Aponta o que falta para que os parâmetros de tempo sejam definidos de forma consistente e o
tempo medido seja comparável ao planejado: marcos de início/fim do apontamento, mão de obra,
equipamento, contorno físico e base de tempo.
Níveis: atencao (compromete a consistência), aviso (recomendado), info.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Espaco, Processo, Recurso
from . import estimativa, modelo_tempo
from .dashboard import alerta_ergonomia


def avaliar(db: Session, empresa_id: int, p: Processo) -> dict:
    ops_out = []
    for e in p.etapas:
        for op in e.operacoes:
            it: list[dict] = []
            add = lambda nivel, msg: it.append({"nivel": nivel, "msg": msg})  # noqa: E731
            if not (op.inicio_marco and op.fim_marco):
                add("atencao", "Defina quando o apontamento começa e termina (marcos). Sem isso, tempos medidos por pessoas "
                               "diferentes não são comparáveis ao planejado.")
            if not op.funcao_requerida:
                add("aviso", "Função (mão de obra) não definida.")
            rec = db.get(Recurso, op.recurso_padrao_id) if op.recurso_padrao_id else None
            if rec is None:
                add("info", "Sem equipamento/posto padrão (ok se a atividade for manual).")
            elif not modelo_tempo.capacidade_por_hora(rec.capacidade, rec.capacidade_unidade):
                add("aviso", f"Equipamento '{rec.nome}' sem capacidade em un/h.")
            if bool(op.espaco_origem_id) != bool(op.espaco_destino_id):
                add("aviso", "Informe espaço de origem e de destino (ou nenhum).")
            if op.espaco_origem_id and op.espaco_destino_id and op.distancia_m is None and modelo_tempo.distancia_entre(
                    db, empresa_id, op.espaco_origem_id, op.espaco_destino_id) is None:
                add("atencao", "Falta a distância entre os espaços de origem e destino.")
            if op.item_peso_kg is None:
                add("info", "Item típico sem peso informado (necessário para manuseio e deslocamento).")
            if alerta_ergonomia(op.ergonomia):
                add("aviso", "Fatores ergonômicos elevados: considere avaliação formal e reflita no tempo.")
            params = estimativa.parametros_vigentes(db, empresa_id, "operacao", op.id)
            m = modelo_tempo.modelo_ativo(db, empresa_id, op.id)
            if "tempo_unitario_min" not in params and m is None:
                add("atencao", "Sem base de tempo: gere o modelo de tempo (IA) ou informe um parâmetro validado.")
            if m is not None:
                r = modelo_tempo.calcular(m.elementos, m.fator_ambiente, modelo_tempo.montar_contexto(db, empresa_id, op, 1.0, None, rec))
                if not r.completo:
                    for f in (r.faltantes or ["modelo sem elementos"]):
                        add("atencao", f"Modelo de tempo incompleto — {f}")
                if m.status_validacao != "validado":
                    add("info", "Modelo de tempo ainda não validado por um gestor.")
                if m.confianca == "baixa":
                    add("info", "Confiança baixa no modelo: meça o tempo real nas primeiras ordens.")
            ops_out.append({"operacao_id": op.id, "nome": f"{e.nome} › {op.nome}", "itens": it,
                            "ok": not any(i["nivel"] == "atencao" for i in it)})
    n = len(ops_out)
    return {"processo_id": p.id, "processo": p.nome, "total_operacoes": n,
            "operacoes_ok": sum(1 for o in ops_out if o["ok"]),
            "pontuacao_pct": round(100 * sum(1 for o in ops_out if o["ok"]) / n, 1) if n else 0.0, "operacoes": ops_out}
