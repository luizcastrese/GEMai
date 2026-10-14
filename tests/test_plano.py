"""Produto (componentes + ligações) → plano de trabalho: contas conferidas à mão, agenda, faltantes e conversão em ordem."""
from datetime import datetime

import pytest

from app.services import plano as svc
from tests.conftest import registrar

FT = 1 / 0.91  # tolerâncias: pessoal 5 % + fadiga básica 4 % (OIT) → FT = 1/(1 − 0,09)


def _cadastrar_contorno(a, u, *, capacidade=30, distancias=True):
    est = a.post("/espacos", {"unidade_id": u, "nome": "Estoque", "tipo": "estoque"}).json()
    cor = a.post("/espacos", {"unidade_id": u, "nome": "Corte", "tipo": "area"}).json()
    mon = a.post("/espacos", {"unidade_id": u, "nome": "Montagem", "tipo": "montagem"}).json()
    if distancias:
        for o, d, m in ((est, cor, 30), (cor, mon, 15)):
            assert a.c.put("/api/v1/distancias", headers=a.h, json={"origem_id": o["id"], "destino_id": d["id"], "metros": m}).status_code == 200
    rec = {"unidade_id": u, "nome": "Seccionadora", "funcao": "corte", "espaco_id": cor["id"]}
    if capacidade:
        rec.update(capacidade=capacidade, capacidade_unidade="un/h")
    assert a.post("/recursos", rec).status_code == 201
    return est, cor, mon


def _mesa(a, parafusos=8):
    """Mesa: Tampo 1,0×0,5×0,02 m (MDF → 7 kg) e 2 Laterais 0,7×0,5×0,02 m (4,9 kg), tudo no grupo Corpo."""
    p = a.post("/produtos", {"nome": "Mesa"}).json()
    base = {"material": "mdf", "espessura_m": 0.02, "largura_m": 0.5}
    tampo = a.post(f"/produtos/{p['id']}/componentes", {"nome": "Tampo", "quantidade": 1, "comprimento_m": 1.0, **base}).json()
    lat = a.post(f"/produtos/{p['id']}/componentes", {"nome": "Lateral", "quantidade": 2, "comprimento_m": 0.7, **base}).json()
    if parafusos:
        assert a.post(f"/produtos/{p['id']}/ligacoes", {"componente_id": lat["id"], "ligado_a_id": tampo["id"],
                                                         "metodo": "parafuso", "fixadores": parafusos}).status_code == 201
    return p["id"], tampo, lat


def _gerar(a, pid, u, **kw):
    r = a.post("/planos", {"produto_id": pid, "unidade_id": u, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_tempos_do_plano_batem_com_a_conta_a_mao(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    por_nome = {s["nome"]: s for s in p["passos"]}
    assert [s["tipo"] for s in p["passos"]] == ["movimentacao", "corte", "movimentacao", "montagem", "inspecao"]
    # peso médio 5,95 kg → 3 peças (20 kg) por viagem; 6 peças = 2 viagens; 30 m, 75 m/min, ida e volta
    assert por_nome["Levar peças até Corte (cortar)"]["tempo_padrao_min"] == pytest.approx(2 * (30 / 75) * 2 * FT, abs=0.01)
    corte = por_nome["Cortar 6 peça(s)"]
    assert corte["tempo_prep_min"] == pytest.approx(5 * FT, abs=0.01)           # preparar a máquina: 5 min de referência
    assert corte["tempo_exec_min"] == pytest.approx(6 / 30 * 60 * FT, abs=0.01)  # 6 peças a 30 un/h
    assert por_nome["Levar peças até a montagem"]["tempo_padrao_min"] == pytest.approx(2 * (15 / 75) * 2 * FT, abs=0.01)
    # montagem: (3 peças × 0,174 min + 8 parafusos × 0,30 min) por unidade × 2 unidades
    assert por_nome["Montar Corpo"]["tempo_padrao_min"] == pytest.approx((3 * 0.174 + 8 * 0.30) * 2 * FT, abs=0.01)
    assert por_nome["Conferência final"]["tempo_padrao_min"] == pytest.approx(5 * 2 * FT, abs=0.01)
    soma = sum(s["tempo_padrao_min"] for s in p["passos"])
    assert p["totais"]["tempo_padrao_min"] == pytest.approx(soma, abs=0.01) and p["totais"]["passos_incompletos"] == 0
    assert p["totais"]["completo"] is True and p["faltantes"] == [] and p["status"] == "rascunho"
    assert p["confianca"] == "baixa" and any("referências genéricas" in x for x in p["premissas"])
    assert any("estimado" in x and "Tampo" in x for x in p["premissas"])      # peso estimado vem rotulado
    # a agenda é encadeada: cada passo começa quando o anterior termina
    for a, b in zip(p["passos"], p["passos"][1:]):
        assert a["fim_prev"] == b["inicio_prev"]


def test_sem_locais_ou_ligacoes_o_plano_diz_o_que_falta_em_vez_de_inventar(admin, unidade_id):
    admin.post("/espacos", {"unidade_id": unidade_id, "nome": "Corte"})
    pid, _, _ = _mesa(admin, parafusos=0)
    p = _gerar(admin, pid, unidade_id)
    texto = " | ".join(p["faltantes"])
    assert "estoque" in texto.lower() and "montagem" in texto.lower() and "Equipamento para 'cortar'" in texto
    assert "Como se montam as peças do grupo 'Corpo'" in texto
    assert p["totais"]["completo"] is False and p["confianca"] == "baixa"
    corte = next(s for s in p["passos"] if s["tipo"] == "corte")
    assert corte["tempo_padrao_min"] is None and corte["inicio_prev"] is None and corte["faltantes"]


def test_equipamento_sem_capacidade_deixa_o_passo_sem_tempo(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id, capacidade=None)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    corte = next(s for s in p["passos"] if s["tipo"] == "corte")
    assert corte["tempo_padrao_min"] is None and any("capacidade" in f for f in corte["faltantes"])
    assert p["totais"]["passos_incompletos"] == 1 and p["totais"]["completo"] is False
    assert any("Quantas peças por hora" in f for f in p["faltantes"])
    # o total soma só o que tem base; o resto fica de fora, nunca como zero
    assert p["totais"]["tempo_padrao_min"] == pytest.approx(sum(s["tempo_padrao_min"] or 0 for s in p["passos"]), abs=0.01)


def test_distancia_nao_cadastrada_e_apontada(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id, distancias=False)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    mov = [s for s in p["passos"] if s["tipo"] == "movimentacao"]
    assert mov and all(s["tempo_padrao_min"] is None and any("distância" in f for f in s["faltantes"]) for s in mov)


def test_referencia_da_empresa_substitui_a_generica(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    antes = next(s for s in _gerar(admin, pid, unidade_id)["passos"] if s["nome"] == "Montar Corpo")["tempo_padrao_min"]
    r = admin.c.put("/api/v1/referencias-tempo", headers=admin.h, json={"chave": "fixador:parafuso", "minutos": 0.5})
    assert r.status_code == 200 and r.json()["informada"] is True and r.json()["padrao_minutos"] == 0.30
    depois = next(s for s in _gerar(admin, pid, unidade_id)["passos"] if s["nome"] == "Montar Corpo")
    assert depois["tempo_padrao_min"] == pytest.approx((3 * 0.174 + 8 * 0.5) * 2 * FT, abs=0.01)
    assert depois["tempo_padrao_min"] > antes
    assert any("da sua oficina" in e["justificativa"] for e in depois["elementos"])
    assert admin.delete("/referencias-tempo/fixador:parafuso").status_code == 204
    lista = {x["chave"]: x for x in admin.get("/referencias-tempo").json()}
    assert lista["fixador:parafuso"]["minutos"] == 0.30 and lista["fixador:parafuso"]["informada"] is False
    assert admin.c.put("/api/v1/referencias-tempo", headers=admin.h, json={"chave": "x y", "minutos": 1}).status_code == 422


def test_tolerancia_do_ambiente_e_alertas_do_local(admin, unidade_id):
    est, cor, mon = _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    base = next(s for s in _gerar(admin, pid, unidade_id)["passos"] if s["tipo"] == "corte")["tempo_padrao_min"]
    assert admin.patch(f"/espacos/{cor['id']}", {"tolerancia_ambiente_pct": 2, "ruido_db": 92, "temperatura_c": 34}).status_code == 200
    p = _gerar(admin, pid, unidade_id)
    corte = next(s for s in p["passos"] if s["tipo"] == "corte")
    assert corte["tempo_padrao_min"] == pytest.approx(17 / 0.89, abs=0.01)                   # 5 % + 4 % + 2 %
    assert corte["tempo_padrao_min"] > base
    assert any("ambiente (Corte)" in t["categoria"] for t in corte["tolerancias"])
    msgs = " ".join(a["msg"] for a in corte["alertas"])
    assert "ruído" in msgs and "temperatura" in msgs and all(a["categoria"] == "seguranca" for a in corte["alertas"])


def _perfil(a, u, nome, **kw):
    r = a.post("/perfis-mao-de-obra", {"unidade_id": u, "nome": nome, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tempo(p, tipo):
    return next(s for s in p["passos"] if s["tipo"] == tipo)["tempo_padrao_min"]


def test_estatura_age_pela_altura_da_bancada(admin, unidade_id):
    """Mesma bancada (95 cm): quem tem o cotovelo longe dela gasta mais fadiga; o efeito é só postural, e é declarado."""
    _, _, mon = _cadastrar_contorno(admin, unidade_id)
    admin.patch(f"/espacos/{mon['id']}", {"altura_trabalho_m": 0.95})
    pid, _, _ = _mesa(admin)
    baixa = _perfil(admin, unidade_id, "Baixa", sexo="feminino", estatura_cm=155)    # cotovelo ≈ 97,7 cm: bancada 2,7 cm abaixo, dentro da faixa
    alta = _perfil(admin, unidade_id, "Alta", sexo="feminino", estatura_cm=190)      # cotovelo ≈ 119,7 cm: bancada 24,7 cm abaixo, 9,7 cm fora
    pb, pa = _gerar(admin, pid, unidade_id, perfil_id=baixa), _gerar(admin, pid, unidade_id, perfil_id=alta)
    assert _tempo(pa, "montagem") > _tempo(pb, "montagem")
    tol = next(t for t in next(s for s in pa["passos"] if s["tipo"] == "montagem")["tolerancias"] if "altura da bancada" in t["categoria"])
    assert tol["percentual"] == pytest.approx(9.7 * 0.4, abs=0.01)
    assert not any("altura da bancada" in t["categoria"] for s in pb["passos"] for t in s["tolerancias"])
    assert _tempo(pa, "corte") == _tempo(pb, "corte")                                  # a máquina não depende de postura do operador
    assert any("Altura do cotovelo estimada" in x for x in pa["premissas"])


def test_sexo_e_peso_corporal_sozinhos_nao_mudam_o_tempo(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    tempos = []
    for sexo, peso in (("feminino", 52), ("misto", 75), ("masculino", 98)):
        perfil = _perfil(admin, unidade_id, f"P-{sexo}", sexo=sexo, estatura_cm=170, peso_corporal_kg=peso)
        tempos.append(_gerar(admin, pid, unidade_id, perfil_id=perfil)["totais"]["tempo_padrao_min"])
    assert len(set(tempos)) == 1                                                       # sem bancada informada, sem limite energético e carga leve: nada muda


def test_sexo_age_pelo_limite_de_carga_e_o_peso_corporal_pelo_gasto_de_energia(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    p = admin.post("/produtos", {"nome": "Painel"}).json()
    admin.post(f"/produtos/{p['id']}/componentes", {"nome": "Chapa", "material": "mdf", "comprimento_m": 2.4, "largura_m": 1.0, "espessura_m": 0.0131})   # ≈ 22 kg
    fem = _perfil(admin, unidade_id, "F", sexo="feminino", estatura_cm=165)
    masc = _perfil(admin, unidade_id, "M", sexo="masculino", estatura_cm=175)
    pf, pm = _gerar(admin, p["id"], unidade_id, perfil_id=fem), _gerar(admin, p["id"], unidade_id, perfil_id=masc)
    mov = lambda pl: next(s for s in pl["passos"] if s["tipo"] == "movimentacao")  # noqa: E731
    assert mov(pf)["pessoas"] == 2 and mov(pm)["pessoas"] == 1                          # 22 kg: acima de 20 kg (CLT), abaixo de 23 kg (NIOSH LC)
    assert any("adulto masculino" in x for x in pm["premissas"]) and any("mais restritivo" in x for x in pf["premissas"])
    # peso corporal: só pesa no tempo quando o limite energético foi informado
    leve = _perfil(admin, unidade_id, "Leve", sexo="feminino", estatura_cm=165, peso_corporal_kg=50, limite_energetico_kcal_min=3.0)
    pesada = _perfil(admin, unidade_id, "Pesada", sexo="feminino", estatura_cm=165, peso_corporal_kg=90, limite_energetico_kcal_min=3.0)
    tl, tp = _gerar(admin, p["id"], unidade_id, perfil_id=leve), _gerar(admin, p["id"], unidade_id, perfil_id=pesada)
    cats = lambda pl: {t["categoria"] for s in pl["passos"] for t in s["tolerancias"]}  # noqa: E731
    assert "ergonomia: gasto de energia (Murrell)" in cats(tp)                          # 3,5 MET × 90 kg × 0,0175 = 5,5 kcal/min > 3,0
    assert tp["totais"]["tempo_padrao_min"] > tl["totais"]["tempo_padrao_min"]


def test_sem_perfil_a_ergonomia_nao_e_considerada_e_o_plano_diz_isso(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    assert any("Ergonomia da equipe NÃO considerada" in x for x in _gerar(admin, pid, unidade_id)["premissas"])


def test_perfil_da_equipe_da_unidade_e_o_padrao_do_plano(admin, unidade_id):
    _, _, mon = _cadastrar_contorno(admin, unidade_id)
    admin.patch(f"/espacos/{mon['id']}", {"altura_trabalho_m": 0.95})
    pid, _, _ = _mesa(admin)
    sem = _gerar(admin, pid, unidade_id)
    alta = _perfil(admin, unidade_id, "Equipe", sexo="masculino", estatura_cm=190)
    assert admin.patch(f"/unidades/{unidade_id}", {"perfil_equipe_id": alta}).json()["perfil_equipe_id"] == alta
    com = _gerar(admin, pid, unidade_id)                                               # sem perfil_id no pedido: usa o da unidade
    assert _tempo(com, "montagem") > _tempo(sem, "montagem")
    outra = admin.post("/unidades", {"nome": "Filial"}).json()
    assert admin.patch(f"/unidades/{outra['id']}", {"perfil_equipe_id": alta}).status_code == 422   # perfil de outra unidade


def test_so_o_ritmo_do_perfil_age_e_apenas_no_trabalho_do_operador(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    lento = admin.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Lento", "ritmo_pct": 80}).json()
    a, b = _gerar(admin, pid, unidade_id), _gerar(admin, pid, unidade_id, perfil_id=lento["id"])
    t = lambda p, tipo: next(s for s in p["passos"] if s["tipo"] == tipo)  # noqa: E731
    assert t(b, "inspecao")["tempo_padrao_min"] == pytest.approx(t(a, "inspecao")["tempo_padrao_min"] / 0.8, abs=0.01)
    # a máquina corta na sua velocidade; só a preparação (feita pelo operador) muda
    assert t(b, "corte")["tempo_exec_min"] == t(a, "corte")["tempo_exec_min"]
    assert t(b, "corte")["tempo_prep_min"] > t(a, "corte")["tempo_prep_min"]


def test_mais_pessoas_quando_a_carga_passa_do_limite_manual(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    p = admin.post("/produtos", {"nome": "Bancada"}).json()
    admin.post(f"/produtos/{p['id']}/componentes", {"nome": "Tampo grande", "material": "mdf", "comprimento_m": 2.5, "largura_m": 1.0, "espessura_m": 0.04})
    plano = _gerar(admin, p["id"], unidade_id)                    # 2,5×1×0,04×700 = 70 kg
    mov = next(s for s in plano["passos"] if s["tipo"] == "movimentacao")
    assert mov["pessoas"] == 4                                    # ceil(70 / 20)
    # 17,5 kg por pessoa no transporte; já o corte, com uma pessoa só, recebe o alerta de peça acima de 60 kg
    assert not any("60 kg" in a["msg"] for s in plano["passos"] if s["tipo"] == "movimentacao" for a in s["alertas"])
    assert any("60 kg" in a["msg"] for s in plano["passos"] if s["tipo"] == "corte" for a in s["alertas"])


def test_agenda_pula_almoco_e_fim_de_semana():
    blocos = [(datetime(2000, 1, 1, 8).time(), datetime(2000, 1, 1, 12).time()), (datetime(2000, 1, 1, 13).time(), datetime(2000, 1, 1, 17).time())]
    # sexta 16:30: 60 min → 30 min na sexta + 30 min na segunda; o seguinte (sem tempo) não anda; o último segue da segunda
    ag = svc.agendar(datetime(2026, 10, 16, 16, 30), blocos, True, [60, None, 30], 0)
    assert ag[0][0] == datetime(2026, 10, 16, 16, 30) and ag[0][1] == datetime(2026, 10, 19, 8, 30)
    assert ag[1][0] == ag[1][1] == datetime(2026, 10, 19, 8, 30) and ag[1][2] is None
    assert ag[2][0] == datetime(2026, 10, 19, 8, 30) and ag[2][1] == datetime(2026, 10, 19, 9, 0)
    # atravessa o almoço
    ag = svc.agendar(datetime(2026, 10, 14, 11, 0), blocos, True, [90], 0)
    assert ag[0][1] == datetime(2026, 10, 14, 13, 30)
    # incluindo fim de semana quando solicitado
    ag = svc.agendar(datetime(2026, 10, 17, 9, 0), blocos, False, [30], 0)
    assert ag[0][1] == datetime(2026, 10, 17, 9, 30)
    # início fora do expediente vai para a próxima abertura
    assert svc.agendar(datetime(2026, 10, 14, 18, 0), blocos, True, [10], 0)[0][0] == datetime(2026, 10, 15, 8, 0)


def test_fadiga_acumulada_informada_alonga_a_duracao():
    blocos = [(datetime(2000, 1, 1, 8).time(), datetime(2000, 1, 1, 12).time()), (datetime(2000, 1, 1, 13).time(), datetime(2000, 1, 1, 17).time())]
    # 13:00 → 4 h já trabalhadas no dia; 5 %/h → +20 %
    ag = svc.agendar(datetime(2026, 10, 14, 13, 0), blocos, True, [60], 5.0)
    assert ag[0][2] == pytest.approx(72.0) and ag[0][1] == datetime(2026, 10, 14, 14, 12)
    assert svc.agendar(datetime(2026, 10, 14, 13, 0), blocos, True, [60], 0)[0][2] == 60


def test_plano_agendado_respeita_os_blocos_da_jornada(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id, blocos=[["08:00", "08:30"], ["09:00", "18:00"]], inicio="2026-10-14T08:00:00-03:00")
    inicio = datetime.fromisoformat(p["passos"][0]["inicio_prev"].replace("Z", "+00:00"))
    fim = datetime.fromisoformat(p["passos"][-1]["fim_prev"].replace("Z", "+00:00"))
    assert (fim - inicio).total_seconds() / 60 > p["totais"]["tempo_padrao_min"] + 29     # a pausa de 30 min está no meio
    assert admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "blocos": [["10:00", "09:00"], ["13:00", "17:00"]]}).status_code == 422
    assert admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "blocos": [["08:00", "12:00"], ["11:00", "17:00"]]}).status_code == 422


def test_alertas_da_jornada_legal():
    bl = lambda *x: [(datetime(2000, 1, 1, int(a[:2]), int(a[3:])).time(), datetime(2000, 1, 1, int(b[:2]), int(b[3:])).time()) for a, b in x]  # noqa: E731
    assert svc.alertas_jornada(bl(("08:00", "12:00"), ("13:00", "17:00"))) == []
    longos = svc.alertas_jornada(bl(("07:00", "12:00"), ("12:10", "19:00")))
    assert len(longos) == 2 and any("8 h" in a["msg"] for a in longos) and any("1 hora" in a["msg"] for a in longos)


def test_confirmacao_e_manual_e_gera_ordem_com_os_tempos_do_plano(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    assert admin.post(f"/planos/{p['id']}/gerar-ordem", {}).status_code == 409           # só depois de confirmar
    assert admin.post(f"/planos/{p['id']}/recalcular", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 3}).json()["quantidade"] == 3
    assert admin.post(f"/planos/{p['id']}/confirmar").json()["status"] == "confirmado"
    assert admin.post(f"/planos/{p['id']}/confirmar").status_code == 409
    assert admin.post(f"/planos/{p['id']}/recalcular", {"produto_id": pid, "unidade_id": unidade_id}).status_code == 409
    r = admin.post(f"/planos/{p['id']}/gerar-ordem", {"cliente": "Cliente X"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["processo_id"] is None and o["plano_id"] == p["id"] and o["quantidade"] == 3 and o["status"] == "planejada"
    plano = admin.get(f"/planos/{p['id']}").json()
    assert len(o["operacoes"]) == len(plano["passos"]) and o["tempo_estimado_min"] == pytest.approx(plano["totais"]["tempo_padrao_min"], abs=0.01)
    assert {x["fonte_estimativa"] for x in o["operacoes"]} == {"plano"} and o["operacoes"][0]["operacao_id"] is None
    assert [x["etapa_nome"] for x in o["operacoes"]][:2] == ["Transporte", "Corte"]
    assert admin.post(f"/planos/{p['id']}/gerar-ordem", {}).status_code == 409           # uma ordem por plano
    assert admin.post(f"/planos/{p['id']}/cancelar").status_code == 409                  # plano com ordem não cancela
    # a ordem segue o fluxo normal: liberar e apontar
    assert admin.post(f"/ordens/{o['id']}/liberar").status_code == 200
    assert admin.get("/operador/fila").json()[0]["fonte_estimativa"] == "plano"


def test_passo_sem_tempo_vira_operacao_sem_base_na_ordem(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id, capacidade=None)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    admin.post(f"/planos/{p['id']}/confirmar")
    o = admin.post(f"/planos/{p['id']}/gerar-ordem", {}).json()
    assert {x["fonte_estimativa"] for x in o["operacoes"]} == {"plano", "sem_base"} and o["estimativa_parcial"] is True


def test_exporta_csv_com_defesa_contra_formulas(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    serra = admin.get("/recursos").json()[0]
    assert admin.patch(f"/recursos/{serra['id']}", {"nome": "=Seccionadora"}).status_code == 200
    p = admin.post("/produtos", {"nome": "Caixa"}).json()
    admin.post(f"/produtos/{p['id']}/componentes", {"nome": "=Tampa", "material": "mdf", "comprimento_m": 0.3, "largura_m": 0.3, "espessura_m": 0.015})
    plano = _gerar(admin, p["id"], unidade_id)
    r = admin.get(f"/planos/{plano['id']}/exportar.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    linhas = r.content.decode("utf-8-sig").splitlines()
    assert linhas[0].startswith("#;Passo;Tipo") and len(linhas) == len(plano["passos"]) + 1
    assert not any(c.startswith("=") for l in linhas for c in l.split(";"))
    assert any(l.startswith("1;") and "'" not in l for l in linhas)               # células vazias continuam vazias
    assert any("'=Seccionadora" in l for l in linhas)                                     # a fórmula virou texto


def test_estrutura_do_produto_validacoes(admin, unidade_id):
    pid, tampo, lat = _mesa(admin)
    assert admin.post(f"/produtos/{pid}/componentes", {"nome": "Tampo"}).status_code == 409
    assert admin.post(f"/produtos/{pid}/ligacoes", {"componente_id": tampo["id"], "ligado_a_id": tampo["id"]}).status_code == 422
    assert admin.post(f"/produtos/{pid}/ligacoes", {"componente_id": 99999}).status_code == 404
    assert admin.post(f"/planos", {"produto_id": admin.post("/produtos", {"nome": "Vazio"}).json()["id"], "unidade_id": unidade_id}).status_code == 422
    est = admin.get(f"/produtos/{pid}/estrutura").json()
    assert est["componentes"][0]["peso_estimado_kg"] == 7.0 and len(est["ligacoes"]) == 1
    assert admin.delete(f"/produtos/{pid}/componentes/{tampo['id']}").status_code == 204
    assert admin.get(f"/produtos/{pid}/estrutura").json()["ligacoes"] == []                # ligações do componente saem junto


def test_interpretar_propoe_e_so_grava_quando_o_usuario_aplica(admin, unidade_id):
    p = admin.post("/produtos", {"nome": "Armário"}).json()
    r = admin.post(f"/produtos/{p['id']}/interpretar",
                   {"descricao": "Armário de MDF com 2 portas, 3 prateleiras, 1 fundo, duas laterais, 4 dobradiças e 1 base"}).json()
    nomes = {c["nome"]: c for c in r["componentes"]}
    assert nomes["Portas"]["quantidade"] == 2 and nomes["Laterais"]["quantidade"] == 2 and nomes["Dobradiças"]["grupo"] == "Ferragens"
    assert "Armário" not in nomes and r["provedor"] == "heuristica"
    assert admin.get(f"/produtos/{p['id']}/estrutura").json()["componentes"] == []          # nada foi salvo
    est = admin.post(f"/produtos/{p['id']}/estrutura", {"componentes": r["componentes"], "ligacoes": [
        {"componente": "Portas", "ligado_a": "Laterais", "metodo": "dobradica", "fixadores": 4},
        {"componente": "Fantasma", "ligado_a": "Laterais", "metodo": "cola", "fixadores": 1}]}).json()
    assert len(est["componentes"]) == 6 and len(est["ligacoes"]) == 1 and est["ligacoes"][0]["metodo"] == "dobradica"


def test_ia_externa_e_validada_e_a_falha_cai_no_provedor_local(admin, unidade_id, monkeypatch):
    from app.services import ia
    from app.services.ia import esquemas as es, heuristica

    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    monkeypatch.setattr(ia, "provedor_ativo", lambda empresa: "claude")
    absurdo = es.PlanoProposta(passos=[es.PassoIA(nome="Passo absurdo", tipo="montagem", pessoas=9999, qtd_pecas=1e12, elementos=[
        es.ElementoTempo(nome="x", metodo="fixo", a_min=9e9)])], confianca="alta")
    monkeypatch.setattr(ia.claude, "planejar", lambda ctx: absurdo)
    p = _gerar(admin, pid, unidade_id)
    s = p["passos"][0]
    assert p["provedor"].startswith("claude") and s["pessoas"] <= 50 and s["qtd_pecas"] <= 1e7 and s["tempo_padrao_min"] <= 100_000 * 2
    assert p["confianca"] != "alta"            # a IA diz "alta", mas sem histórico medido o sistema não repassa isso
    def falha(ctx):
        raise RuntimeError("sem rede")
    monkeypatch.setattr(ia.claude, "planejar", falha)
    p = _gerar(admin, pid, unidade_id)
    assert p["provedor"] == heuristica.NOME and any("provedor local" in x for x in p["premissas"])


def test_isolamento_entre_empresas(client, admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, tampo, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    b = registrar(client, "Empresa B")
    assert b.get(f"/planos/{p['id']}").status_code == 404
    assert b.get(f"/planos/{p['id']}/exportar.csv").status_code == 404
    assert b.post(f"/planos/{p['id']}/confirmar").status_code == 404
    assert b.get(f"/produtos/{pid}/estrutura").status_code == 404
    assert b.post(f"/produtos/{pid}/componentes", {"nome": "X"}).status_code == 404
    assert b.delete(f"/produtos/{pid}/componentes/{tampo['id']}").status_code == 404
    assert b.post("/planos", {"produto_id": pid, "unidade_id": b.unidade_id}).status_code == 404
    assert b.post("/planos", {"produto_id": b.post("/produtos", {"nome": "P"}).json()["id"], "unidade_id": unidade_id}).status_code == 404
    assert b.get("/planos").json() == []
    assert [x["id"] for x in admin.get("/planos").json()] == [p["id"]]


def test_usuario_restrito_a_outra_unidade_nao_ve_o_plano(admin, unidade_id):
    from tests.conftest import criar_usuario
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    outra = admin.post("/unidades", {"nome": "Filial"}).json()
    restrito = criar_usuario(admin, "filial@a.com", [outra["id"]])
    assert restrito.get(f"/planos/{p['id']}").status_code == 404
    assert restrito.post("/planos", {"produto_id": pid, "unidade_id": unidade_id}).status_code == 404
