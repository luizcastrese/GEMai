"""Fluxo completo do documento: descrição → IA → estrutura → ordem → apontamento → análise."""
from datetime import date, datetime, timedelta, timezone

from tests.conftest import montar_processo


def test_implantacao_com_ia_ate_ordem(admin, gestor, unidade_id):
    # Tela 1
    r = gestor.patch(f"/unidades/{unidade_id}", {
        "descricao_operacao": "Recebemos insumos, preparamos, produzimos e entregamos.",
        "objetivo": "Reduzir tempo e padronizar produção", "principais_problemas": "Atrasos, retrabalho e falta de histórico"})
    assert r.status_code == 200
    # Tela 2 – perguntas adaptativas
    g = gestor.post(f"/unidades/{unidade_id}/diagnostico/perguntas/gerar").json()
    assert g["provedor"] == "heuristica" and len(g["perguntas"]) >= 5
    grupos = {p["grupo"] for p in g["perguntas"]}
    assert {"Processos", "Recursos", "Qualidade"} <= grupos  # "retrabalho" disparou aprofundamento de Qualidade
    por_grupo = {p["grupo"]: p for p in g["perguntas"]}
    gestor.patch(f"/diagnostico/perguntas/{por_grupo['Processos']['id']}",
                 {"resposta": "1. Corte\n2. Colagem\n3. Montagem"})
    gestor.patch(f"/diagnostico/perguntas/{por_grupo['Recursos']['id']}", {"resposta": "Serra circular, Bancada 1"})
    # segunda rodada não repete perguntas
    g2 = gestor.post(f"/unidades/{unidade_id}/diagnostico/perguntas/gerar").json()
    textos1 = {p["texto"] for p in g["perguntas"]}
    assert not textos1 & {p["texto"] for p in g2["perguntas"]}

    # Tela 3 – estrutura sugerida (pendente, nada criado ainda)
    rec = gestor.post(f"/unidades/{unidade_id}/diagnostico/estruturar").json()
    assert rec["status"] == "pendente" and "Sugestão" in rec["aviso"]
    etapas = [e["nome"] for e in rec["conteudo"]["processos"][0]["etapas"]]
    assert etapas == ["Corte", "Colagem", "Montagem"]
    assert gestor.get("/processos").json() == []
    assert {r["nome"] for r in rec["conteudo"]["recursos"]} == {"Serra circular", "Bancada 1"}
    assert "Inspeção / conferência de qualidade" in rec["conteudo"]["etapas_possivelmente_omitidas"]

    # usuário revisa: remove a etapa "Colagem" e aprova
    c = rec["conteudo"]
    c["processos"][0]["etapas"] = [e for e in c["processos"][0]["etapas"] if e["nome"] != "Colagem"]
    assert gestor.patch(f"/recomendacoes/{rec['id']}", {"conteudo": c}).status_code == 200
    ap = gestor.post(f"/recomendacoes/{rec['id']}/aprovar", {"observacao": "ok"}).json()
    assert ap["status"] == "aplicada" and ap["evidencias"]["aplicado"]["etapas"] == 2
    assert gestor.post(f"/recomendacoes/{rec['id']}/aprovar").status_code == 409  # não aplica duas vezes

    proc = gestor.get("/processos").json()[0]
    assert proc["status"] == "rascunho" and proc["origem"] == "ia"
    det = gestor.get(f"/processos/{proc['id']}").json()
    assert [e["nome"] for e in det["etapas"]] == ["Corte", "Montagem"]
    op_ids = [e["operacoes"][0]["id"] for e in det["etapas"]]

    # parâmetros da IA nascem pendentes e NÃO entram no cálculo
    params = gestor.get(f"/parametros?escopo_tipo=operacao&escopo_id={op_ids[0]}").json()
    assert params and all(p["origem"] == "ia_sugerido" and p["status_validacao"] == "pendente" and not p["vigente"] for p in params)
    assert gestor.post(f"/parametros/{params[0]['id']}/validar").status_code == 422  # sem valor: precisa ser medido

    # ordem exige processo ativo
    assert gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": proc["id"], "quantidade": 3}).status_code == 409
    pub = gestor.post(f"/processos/{proc['id']}/publicar").json()
    assert pub["status"] == "ativo" and len(pub["avisos"]) == 2
    ordem = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": proc["id"], "quantidade": 3,
                                    "cliente": "Cliente X"}).json()
    assert ordem["tempo_estimado_min"] is None and ordem["estimativa_parcial"]  # sem base: nada inventado
    assert {o["fonte_estimativa"] for o in ordem["operacoes"]} == {"sem_base"}


def test_ciclo_de_producao_e_analise(admin, gestor, operador, unidade_id):
    pid, ops = montar_processo(gestor, unidade_id, tempo_unit=2.0, tempo_prep=10.0)
    hoje = date.today()
    ordem = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 10,
                                    "cliente": "C", "prazo": (hoje + timedelta(days=3)).isoformat()}).json()
    # estimativa: 2 operações × (10 + 2*10) = 60
    assert ordem["tempo_estimado_min"] == 60 and ordem["status"] == "planejada"
    assert {o["fonte_estimativa"] for o in ordem["operacoes"]} == {"parametro"}
    oid = ordem["id"]
    op1, op2 = [o["id"] for o in ordem["operacoes"]]

    # não aponta antes de liberar
    assert operador.post("/apontamentos/iniciar", {"ordem_operacao_id": op1}).status_code == 409
    assert gestor.post(f"/ordens/{oid}/liberar").json()["status"] == "liberada"

    # operador inicia e finaliza (tempos reais retroativos via gestor para controlar o relógio)
    a = operador.post("/apontamentos/iniciar", {"ordem_operacao_id": op1}).json()
    assert a["fim"] is None
    assert operador.post("/apontamentos/iniciar", {"ordem_operacao_id": op2}).status_code == 409  # já tem um aberto
    assert gestor.get(f"/ordens/{oid}").json()["status"] == "em_producao"
    assert [x["id"] for x in operador.get("/apontamentos/abertos").json()] == [a["id"]]
    f = operador.post(f"/apontamentos/{a['id']}/finalizar", {"quantidade_boa": 10})
    assert f.status_code == 200 and f.json()["fim"]
    assert operador.post(f"/ordens/{oid}/operacoes/{op1}/concluir").status_code == 200

    # lançamento manual (gestor) para a 2ª operação: 30 min de execução + 5 de retrabalho, 1 refugo
    agora = datetime.now(timezone.utc)
    base = agora - timedelta(hours=3)
    m1 = gestor.post("/apontamentos", {"ordem_operacao_id": op2, "tipo": "preparacao",
                                       "inicio": base.isoformat(), "fim": (base + timedelta(minutes=10)).isoformat()})
    assert m1.status_code == 201, m1.text
    m2 = gestor.post("/apontamentos", {"ordem_operacao_id": op2, "tipo": "execucao", "dados_extras": {"temperatura": 21.5},
                                       "inicio": (base + timedelta(minutes=10)).isoformat(),
                                       "fim": (base + timedelta(minutes=40)).isoformat(),
                                       "quantidade_boa": 9, "quantidade_refugo": 1})
    assert m2.status_code == 201, m2.text
    m3 = gestor.post("/apontamentos", {"ordem_operacao_id": op2, "tipo": "retrabalho",
                                       "inicio": (base + timedelta(minutes=40)).isoformat(),
                                       "fim": (base + timedelta(minutes=45)).isoformat(), "quantidade_boa": 1})
    assert m3.status_code == 201
    # validação de campos extras
    ruim = gestor.post("/apontamentos", {"ordem_operacao_id": op2, "tipo": "execucao", "dados_extras": {"pressao": 3},
                                         "inicio": base.isoformat(), "fim": (base + timedelta(minutes=1)).isoformat()})
    assert ruim.status_code == 422
    # não conclui ordem com operação pendente
    assert gestor.post(f"/ordens/{oid}/concluir").status_code == 409
    gestor.post(f"/ordens/{oid}/operacoes/{op2}/concluir")
    assert gestor.post(f"/ordens/{oid}/concluir").json()["status"] == "concluida"

    an = gestor.get(f"/ordens/{oid}/analise").json()
    s = an["resumo"]
    assert s["estimado_min"] == 60 and s["refugo"] == 1 and s["retrabalho_min"] == 5
    op2m = next(o for o in an["operacoes"] if o["ordem_operacao_id"] == op2)
    assert op2m["realizado_min"] == 45 and op2m["estimado_min"] == 30 and op2m["desvio_min"] == 15
    assert op2m["desvio_pct"] == 50
    dash = gestor.get("/dashboard").json()
    assert dash["ordens"]["concluidas_no_periodo"] == 1 and dash["qualidade"]["refugo"] == 1
    assert dash["retrabalho"]["tempo_min"] == 5

    # histórico só vale depois da aprovação
    assert gestor.post(f"/operacoes/{ops[1]}/parametros/atualizar-historico").status_code == 409
    for x in gestor.get(f"/apontamentos?ordem_id={oid}").json():
        if x["fim"]:
            assert gestor.post(f"/apontamentos/{x['id']}/aprovar").status_code == 200
    assert gestor.post(f"/apontamentos/{a['id']}/aprovar").status_code == 409  # já decidido


def test_historico_aprovado_melhora_estimativa(gestor, unidade_id):
    pid, ops = montar_processo(gestor, unidade_id, tempo_unit=2.0, tempo_prep=0.0)
    agora = datetime.now(timezone.utc)
    # 3 ordens concluídas em que a operação 1 levou 3 min/un (e não os 2 informados)
    for i in range(3):
        o = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 10}).json()
        gestor.post(f"/ordens/{o['id']}/liberar")
        oo = o["operacoes"][0]["id"]
        ini = agora - timedelta(hours=10 - i)
        a = gestor.post("/apontamentos", {"ordem_operacao_id": oo, "tipo": "execucao", "inicio": ini.isoformat(),
                                          "fim": (ini + timedelta(minutes=30)).isoformat(), "quantidade_boa": 10}).json()
        gestor.post(f"/ordens/{o['id']}/operacoes/{oo}/concluir")
        if i < 2:
            gestor.post(f"/apontamentos/{a['id']}/aprovar")
    nova = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 10}).json()
    assert nova["operacoes"][0]["fonte_estimativa"] == "parametro"  # só 2 aprovadas (<3)
    # terceira aprovação libera o histórico
    ap = [x for x in gestor.get("/apontamentos?status=registrado").json()]
    gestor.post(f"/apontamentos/{ap[0]['id']}/aprovar")
    nova = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 10}).json()
    assert nova["operacoes"][0]["fonte_estimativa"] == "historico"
    assert nova["operacoes"][0]["tempo_exec_est_min"] == 30  # 3 min/un × 10
    # a operação 2 continua só com parâmetro
    assert nova["operacoes"][1]["fonte_estimativa"] == "parametro"
    # recalibração explícita grava nova versão do parâmetro, rastreável
    novos = gestor.post(f"/operacoes/{ops[0]}/parametros/atualizar-historico").json()
    assert novos[0]["origem"] == "calculado" and novos[0]["valor_num"] == 3 and novos[0]["versao"] == 2
    hist = gestor.get(f"/parametros?escopo_tipo=operacao&escopo_id={ops[0]}&historico=true").json()
    assert [p["vigente"] for p in hist if p["nome"] == "tempo_unitario_min"] == [True, False]
