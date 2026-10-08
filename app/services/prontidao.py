"""Prontidão do processo para o gêmeo digital (checagem determinística, sem IA).

Aponta o que falta para que os parâmetros de tempo sejam definidos de forma consistente e o
tempo medido seja comparável ao planejado: marcos de início/fim do apontamento, mão de obra,
equipamento, contorno físico e base de tempo.
Níveis: atencao (compromete a consistência), aviso (recomendado), info.
Categorias (para a interface decidir o que mostrar): `simples` (qualquer usuário entende e resolve),
`seguranca` (sempre visível, em linguagem simples) e `tecnico` (só no modo especialista).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Espaco, PerfilMaoDeObra, Processo, Recurso
from . import ergonomia, estimativa, modelo_tempo
from .dashboard import alerta_ergonomia


def _alerta_simples(a: str) -> tuple[str, str]:
    """(texto em linguagem comum, categoria). O texto técnico original segue em `detalhe`."""
    if "Índice de levantamento" in a:
        return ("Segurança: a carga desta tarefa está acima do limite recomendado para levantamento manual. "
                "Use ajuda mecânica, divida a carga ou peça uma avaliação ergonômica."), "seguranca"
    if "art. 198" in a:
        return "Segurança: uma peça acima de 60 kg não deve ser carregada por uma pessoa só. Use meio mecânico ou mais gente.", "seguranca"
    if "arts. 390" in a:
        return ("Segurança: a carga está acima do limite de referência para o perfil de quem executa. "
                "Confirme as regras aplicáveis com a área de segurança do trabalho."), "seguranca"
    if "NR-15" in a:
        return "Segurança: o ruído neste local está alto. Verifique a proteção auditiva e o tempo de exposição.", "seguranca"
    return a, "tecnico"  # ex.: comparação com a altura do cotovelo


def avaliar(db: Session, empresa_id: int, p: Processo) -> dict:
    ops_out = []
    for e in p.etapas:
        for op in e.operacoes:
            it: list[dict] = []
            add = lambda nivel, msg, cat="simples", detalhe="": it.append(  # noqa: E731
                {"nivel": nivel, "msg": msg, "categoria": cat, "detalhe": detalhe})
            if not (op.inicio_marco and op.fim_marco):
                add("atencao", "Diga quando a tarefa começa e quando termina (ex.: pega a primeira peça / solta a última). "
                               "Assim, os tempos medidos por pessoas diferentes ficam comparáveis.")
            if not op.funcao_requerida:
                add("aviso", "Função (mão de obra) não definida.", "tecnico")
            rec = db.get(Recurso, op.recurso_padrao_id) if op.recurso_padrao_id else None
            if rec is None:
                add("info", "Sem equipamento/posto padrão (ok se a atividade for manual).", "tecnico")
            elif not modelo_tempo.capacidade_por_hora(rec.capacidade, rec.capacidade_unidade):
                add("aviso", f"Informe a capacidade do equipamento '{rec.nome}' (peças por hora) para a IA prever o tempo de máquina.")
            if bool(op.espaco_origem_id) != bool(op.espaco_destino_id):
                add("aviso", "Informe de onde a peça sai e para onde vai (ou deixe os dois em branco).")
            if op.espaco_origem_id and op.espaco_destino_id and op.distancia_m is None and modelo_tempo.distancia_entre(
                    db, empresa_id, op.espaco_origem_id, op.espaco_destino_id) is None:
                add("atencao", "Informe a distância entre os dois locais (em Equipamentos e locais › Locais).")
            if op.item_peso_kg is None:
                add("info", "Informe o peso da peça para a previsão considerar o manuseio e o transporte.")
            if alerta_ergonomia(op.ergonomia):
                add("aviso", "Esta tarefa exige muito esforço físico: considere uma avaliação ergonômica.", "seguranca")
            perfil = db.get(PerfilMaoDeObra, op.perfil_id) if op.perfil_id else None
            if perfil is None:
                add("aviso", "Sem perfil de mão de obra: o ritmo e os limites de carga não podem ser considerados.", "tecnico")
            if not op.postura_trabalho:
                add("info", "Postura de trabalho não informada (afeta a tolerância por fadiga).", "tecnico")
            if op.levantamento and not ergonomia.niosh(op.levantamento, op.item_peso_kg).get("completo"):
                add("atencao", "Dados de levantamento (NIOSH) incompletos: " + "; ".join(ergonomia.niosh(op.levantamento, op.item_peso_kg)["faltantes"]), "tecnico")
            esps = [db.get(Espaco, i) for i in (op.espaco_origem_id, op.espaco_destino_id) if i]
            erg = ergonomia.avaliar_operacao(op, perfil, esps, op.item_peso_kg)
            for a in erg["alertas"]:
                txt, cat = _alerta_simples(a)
                add("atencao" if cat == "seguranca" else "aviso", txt, cat, a)
            params = estimativa.parametros_vigentes(db, empresa_id, "operacao", op.id)
            m = modelo_tempo.modelo_ativo(db, empresa_id, op.id)
            if "tempo_unitario_min" not in params and m is None:
                add("atencao", "Ainda sem previsão de tempo: peça à IA para estimar ou informe o tempo medido.")
            if m is not None:
                r = modelo_tempo.calcular(m.elementos, m.fator_ambiente, modelo_tempo.montar_contexto(db, empresa_id, op, 1.0, None, rec),
                                          m.tolerancias, m.ritmo_pct)
                if not r.completo:
                    for f in (r.faltantes or ["dados do contorno físico"]):
                        add("atencao", f"Para prever o tempo falta: {f}")
                if m.status_validacao == "pendente":
                    add("info", "A previsão da IA aguarda a sua confirmação.")
                if m.confianca == "baixa":
                    add("info", "Confiança baixa no modelo: meça o tempo real nas primeiras ordens.", "tecnico")
            ops_out.append({"operacao_id": op.id, "nome": op.nome if e.nome == op.nome else f"{e.nome} › {op.nome}", "itens": it,
                            "ok": not any(i["nivel"] == "atencao" and i["categoria"] != "tecnico" for i in it)})
    n = len(ops_out)
    return {"processo_id": p.id, "processo": p.nome, "total_operacoes": n,
            "operacoes_ok": sum(1 for o in ops_out if o["ok"]),
            "pontuacao_pct": round(100 * sum(1 for o in ops_out if o["ok"]) / n, 1) if n else 0.0, "operacoes": ops_out}
