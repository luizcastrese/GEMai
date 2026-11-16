"""Produto = família ("Mesa"); tamanho, tipo e parafusos de CADA pedido ficam no plano. Relatório produto × variante × tempo."""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Apontamento, Ordem, OrdemOperacao
from tests.conftest import registrar
from tests.test_plano import _cadastrar_contorno, _mesa

CAMPOS = [{"nome": "Largura", "tipo": "numero", "unidade": "cm", "obrigatorio": True},
          {"nome": "Tipo", "tipo": "opcao", "opcoes": ["Simples", "Reforçada"]},
          {"nome": "Acabamento", "tipo": "texto"}]


def _produto_com_campos(a, u, parafusos=8):
    _cadastrar_contorno(a, u)
    pid, _, _ = _mesa(a, parafusos)
    r = a.patch(f"/produtos/{pid}", {"campos_especificacao": CAMPOS})
    assert r.status_code == 200, r.text
    return pid


def _plano(a, pid, u, espec=None, estrutura=None, **kw):
    corpo = {"produto_id": pid, "unidade_id": u, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00", **kw}
    if espec is not None:
        corpo["especificacoes"] = espec
    if estrutura is not None:
        corpo["estrutura"] = estrutura
    return a.post("/planos", corpo)


# ------------------------------------------------------------------ campos do produto
def test_produto_guarda_os_campos_de_especificacao(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    p = admin.get(f"/produtos/{pid}").json()
    assert [c["nome"] for c in p["campos_especificacao"]] == ["Largura", "Tipo", "Acabamento"]
    assert p["campos_especificacao"][1]["opcoes"] == ["Simples", "Reforçada"]


@pytest.mark.parametrize("campos", [
    [{"nome": "Tipo", "tipo": "opcao", "opcoes": ["Só uma"]}],                     # escolha precisa de 2+ opções
    [{"nome": "Largura"}, {"nome": "largura"}],                                     # nome repetido (sem diferenciar maiúscula)
    [{"nome": "X", "tipo": "livre"}],                                               # tipo inexistente
])
def test_campos_invalidos_sao_recusados(admin, unidade_id, campos):
    pid = _produto_com_campos(admin, unidade_id)
    assert admin.patch(f"/produtos/{pid}", {"campos_especificacao": campos}).status_code == 422


# ------------------------------------------------------------------ valores do pedido
def test_plano_guarda_a_variante_e_ela_aparece_no_nome(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    r = _plano(admin, pid, unidade_id, {"Largura": "80,5", "Tipo": "reforçada"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["especificacoes"] == {"Largura": 80.5, "Tipo": "Reforçada"}      # número vira número; opção volta com a grafia do cadastro
    assert p["nome"] == "Mesa (Largura 80.5 cm · Tipo Reforçada) × 2"
    assert admin.get(f"/planos/{p['id']}").json()["especificacoes"] == p["especificacoes"]
    assert p["variante"] == "Largura 80.5 cm · Tipo Reforçada"
    assert admin.get("/planos").json()[0]["variante"] == p["variante"] and admin.get("/planos").json()[0]["estrutura"] is None   # lista não traz a estrutura


@pytest.mark.parametrize("espec,trecho", [
    ({"Altura": 10, "Largura": 80}, "Altura"),                  # campo que o produto não tem
    ({"Largura": "abc"}, "número"),
    ({"Largura": -3}, "número"),
    ({"Largura": 80, "Tipo": "Dourada"}, "opções"),
    ({"Tipo": "Simples"}, "Preencha"),                          # falta o obrigatório
])
def test_valores_do_pedido_sao_validados_contra_o_produto(admin, unidade_id, espec, trecho):
    pid = _produto_com_campos(admin, unidade_id)
    r = _plano(admin, pid, unidade_id, espec)
    assert r.status_code == 422 and trecho in r.json()["detail"]


def test_produto_sem_campos_nao_aceita_valores(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    r = _plano(admin, pid, unidade_id, {"Largura": 80})
    assert r.status_code == 422 and "campos de especificação" in r.json()["detail"]
    assert _plano(admin, pid, unidade_id).status_code == 201          # sem valores continua funcionando como antes


# ------------------------------------------------------------------ peças e parafusos do pedido
def test_modelo_base_vem_por_nome_e_serve_de_partida(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id, parafusos=8)
    mb = admin.get(f"/produtos/{pid}/modelo-base").json()
    assert [c["nome"] for c in mb["componentes"]] == ["Tampo", "Lateral"]
    assert mb["ligacoes"] == [{"componente": "Lateral", "ligado_a": "Tampo", "metodo": "parafuso", "fixadores": 8, "formula_fixadores": ""}]
    assert all(c["formulas"] == {} for c in mb["componentes"])


def test_estrutura_do_pedido_muda_o_tempo_sem_mexer_no_produto(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id, parafusos=8)
    base = _plano(admin, pid, unidade_id, {"Largura": 80}).json()
    mb = admin.get(f"/produtos/{pid}/modelo-base").json()
    mb["ligacoes"][0]["fixadores"] = 20                              # este pedido leva 20 parafusos em vez de 8
    maior = _plano(admin, pid, unidade_id, {"Largura": 120}, mb).json()

    def montagem(p):
        return next(s for s in p["passos"] if s["modulo"] == "montagem")["tempo_padrao_min"]
    # 12 parafusos a mais × 0,30 min × 2 unidades, com as tolerâncias de 9 %
    assert montagem(maior) - montagem(base) == pytest.approx(12 * 0.30 * 2 / 0.91, abs=0.02)
    assert admin.get(f"/produtos/{pid}/modelo-base").json()["ligacoes"][0]["fixadores"] == 8      # o produto continua igual
    assert admin.get(f"/planos/{maior['id']}").json()["estrutura"]["ligacoes"][0]["fixadores"] == 20


def test_estrutura_com_referencia_inexistente_ou_nome_repetido_e_recusada(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    comp = {"nome": "Tampo", "quantidade": 1}
    assert _plano(admin, pid, unidade_id, estrutura={"componentes": [comp], "ligacoes": [{"componente": "Perna", "fixadores": 2}]}).status_code == 422
    assert _plano(admin, pid, unidade_id, estrutura={"componentes": [comp, comp]}).status_code == 422
    assert _plano(admin, pid, unidade_id, estrutura={"componentes": []}).status_code == 422


def test_recalcular_mantem_a_variante_quando_nao_vem_nova(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    mb = admin.get(f"/produtos/{pid}/modelo-base").json()
    mb["ligacoes"][0]["fixadores"] = 12
    p = _plano(admin, pid, unidade_id, {"Largura": 90}, mb).json()
    r = admin.post(f"/planos/{p['id']}/recalcular", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 3,
                                                      "inicio": "2026-10-14T08:00:00-03:00"})
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["quantidade"] == 3 and n["especificacoes"] == {"Largura": 90.0}
    assert admin.get(f"/planos/{p['id']}").json()["estrutura"]["ligacoes"][0]["fixadores"] == 12
    trocou = admin.post(f"/planos/{p['id']}/recalcular", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 3,
                                                           "especificacoes": {"Largura": 100}, "inicio": "2026-10-14T08:00:00-03:00"})
    assert trocou.json()["especificacoes"] == {"Largura": 100.0}


def test_arranjo_e_ordem_levam_a_variante(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    r = admin.post("/planos/arranjos", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 2, "especificacoes": {"Largura": 80}})
    assert r.status_code == 200, r.text
    p = _plano(admin, pid, unidade_id, {"Largura": 80, "Tipo": "Simples"}).json()
    assert admin.post(f"/planos/{p['id']}/confirmar").status_code == 200
    o = admin.post(f"/planos/{p['id']}/gerar-ordem", {"cliente": "Maria"})
    assert o.status_code == 201, o.text
    assert o.json()["descricao"] == "Mesa (Largura 80 cm · Tipo Simples)"


# ------------------------------------------------------------------ relatório
def _concluir(db_factory, quem, plano_id, minutos_por_passo):
    """Simula a execução: apontamentos em cada passo da ordem do plano e ordem concluída."""
    db = db_factory()
    try:
        o = db.query(Ordem).filter(Ordem.plano_id == plano_id).one()
        t0 = datetime(2026, 10, 15, 8, tzinfo=timezone.utc)
        for i, oo in enumerate(db.query(OrdemOperacao).filter(OrdemOperacao.ordem_id == o.id).order_by(OrdemOperacao.sequencia)):
            ini = t0 + timedelta(hours=i)
            db.add(Apontamento(empresa_id=o.empresa_id, unidade_id=o.unidade_id, ordem_id=o.id, ordem_operacao_id=oo.id, tipo="execucao",
                               inicio=ini, fim=ini + timedelta(minutes=minutos_por_passo), quantidade_boa=o.quantidade, status="aprovado",
                               registrado_por=quem["id"]))
            oo.status = "concluida"
        o.status, o.concluida_em = "concluida", t0 + timedelta(days=1)
        db.commit()
    finally:
        db.close()


def _pedido(admin, pid, u, espec, db_factory=None, minutos=None, estrutura=None):
    p = _plano(admin, pid, u, espec, estrutura).json()
    if minutos is not None:
        assert admin.post(f"/planos/{p['id']}/confirmar").status_code == 200
        assert admin.post(f"/planos/{p['id']}/gerar-ordem", {"cliente": "Cliente X"}).status_code == 201
        _concluir(db_factory, admin.usuario, p["id"], minutos)
    return p


def test_relatorio_cruza_produto_variante_previsto_e_realizado(admin, unidade_id, db_factory):
    pid = _produto_com_campos(admin, unidade_id)
    a = _pedido(admin, pid, unidade_id, {"Largura": 80, "Tipo": "Simples"}, db_factory, minutos=10)        # 5 passos × 10 = 50 min
    _pedido(admin, pid, unidade_id, {"Largura": 80, "Tipo": "Simples"}, db_factory, minutos=14)           # outro pedido da MESMA variante: 70 min
    c = _pedido(admin, pid, unidade_id, {"Largura": 120, "Tipo": "Reforçada"})                             # variante diferente, só planejada
    r = admin.get(f"/relatorios/desempenho?produto_id={pid}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["campos"] == ["Largura", "Tipo", "Acabamento"] and len(d["linhas"]) == 3
    linha = next(l for l in d["linhas"] if l["plano_id"] == a["id"])
    assert linha["variante"] == "Largura 80 cm · Tipo Simples" and linha["ordem_numero"] and linha["cliente"] == "Cliente X"
    assert linha["realizado_min"] == 50 and linha["realizado_por_unidade_min"] == 25 and linha["comparavel"] is True
    assert linha["previsto_min"] == pytest.approx(a["totais"]["tempo_padrao_min"], abs=0.01)
    assert linha["desvio_min"] == pytest.approx(50 - a["totais"]["tempo_padrao_min"], abs=0.02)
    so_plano = next(l for l in d["linhas"] if l["plano_id"] == c["id"])
    assert so_plano["realizado_min"] is None and so_plano["comparavel"] is False and so_plano["previsto_por_unidade_min"]
    # resumo: 2 variantes; a de 80 cm junta os dois pedidos concluídos (4 un, 120 min → 30 min/un)
    res = {s["variante"]: s for s in d["resumo"]}
    assert set(res) == {"Largura 80 cm · Tipo Simples", "Largura 120 cm · Tipo Reforçada"}
    s80 = res["Largura 80 cm · Tipo Simples"]
    assert s80["planos"] == 2 and s80["ordens_concluidas"] == 2 and s80["quantidade_concluida"] == 4
    assert s80["realizado_por_unidade_min"] == 30
    assert s80["desvio_pct"] == pytest.approx((120 - 2 * a["totais"]["tempo_padrao_min"]) / (2 * a["totais"]["tempo_padrao_min"]) * 100, abs=0.2)
    s120 = res["Largura 120 cm · Tipo Reforçada"]
    assert s120["ordens_concluidas"] == 0 and s120["realizado_por_unidade_min"] is None and s120["desvio_pct"] is None
    assert s120["previsto_por_unidade_planos_min"] > 0


def test_csv_do_relatorio_tem_uma_coluna_por_campo_e_defesa_de_formula(admin, unidade_id, db_factory):
    pid = _produto_com_campos(admin, unidade_id)
    _pedido(admin, pid, unidade_id, {"Largura": 80, "Tipo": "Simples", "Acabamento": "=HYPERLINK(\"x\")"}, db_factory, minutos=10)
    r = admin.get(f"/relatorios/desempenho.csv?produto_id={pid}&tipo=detalhe")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and r.content.startswith(b"\xef\xbb\xbf")
    linhas = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    cab = linhas[0]
    assert cab[:7] == ["Produto", "Pedido (plano)", "Unidade", "Criado em", "Largura", "Tipo", "Acabamento"]
    assert "Tempo realizado total (min)" in cab and "Desvio (%)" in cab
    cel = linhas[1]
    assert cel[0] == "Mesa" and cel[4] == "80" and cel[5] == "Simples" and cel[6].startswith("'=HYPERLINK")      # fórmula neutralizada
    assert cel[cab.index("Tempo realizado total (min)")] == "50" and cel[cab.index("Situação da ordem")] == "Concluída"
    resumo = admin.get(f"/relatorios/desempenho.csv?produto_id={pid}&tipo=resumo").content.decode("utf-8-sig").splitlines()
    assert resumo[0].startswith("Produto;Largura;Tipo;Acabamento;Planos;Ordens concluídas") and len(resumo) == 2
    # sem filtrar produto, as especificações viram uma coluna só
    geral = admin.get("/relatorios/desempenho.csv").content.decode("utf-8-sig").splitlines()[0].split(";")
    assert "Especificações" in geral and "Largura" not in geral


def test_relatorio_filtra_por_periodo_e_ignora_planos_cancelados(admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    p1 = _plano(admin, pid, unidade_id, {"Largura": 80}).json()
    p2 = _plano(admin, pid, unidade_id, {"Largura": 90}).json()
    admin.post(f"/planos/{p2['id']}/cancelar")
    ids = [l["plano_id"] for l in admin.get("/relatorios/desempenho").json()["linhas"]]
    assert ids == [p1["id"]]
    assert admin.get("/relatorios/desempenho?desde=2999-01-01").json()["linhas"] == []
    assert admin.get("/relatorios/desempenho?ate=2000-01-01").json()["linhas"] == []
    assert len(admin.get("/relatorios/desempenho?desde=2000-01-01&ate=2999-12-31").json()["linhas"]) == 1
    assert admin.get("/relatorios/desempenho?desde=ontem").status_code == 422


def test_relatorio_respeita_empresa_e_unidade(client, admin, unidade_id):
    pid = _produto_com_campos(admin, unidade_id)
    _plano(admin, pid, unidade_id, {"Largura": 80})
    outra = registrar(client, "Empresa B")
    assert outra.get("/relatorios/desempenho").json()["linhas"] == []
    assert outra.get(f"/relatorios/desempenho?produto_id={pid}").status_code == 404        # produto de outra empresa
    assert outra.get(f"/relatorios/desempenho.csv?unidade_id={unidade_id}").status_code == 404
