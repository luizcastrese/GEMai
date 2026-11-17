"""Calibração por família: pedidos do mesmo produto com tamanhos diferentes compartilham o núcleo de cálculo, e o erro do
módulo é aprendido como função do porte (o que os pedidos maiores ensinam serve para os menores)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Apontamento, Ordem, OrdemOperacao
from app.services import calibracao_modulos as svc
from tests.test_plano import _cadastrar_contorno, _mesa

PORTE_BASE = 3 * 0.174 + 8 * 0.30  # tempo normal da montagem por unidade da mesa-base (8 parafusos) = 2,922 min/un


def _ordens_de_montagem(db_factory, admin, unidade_id, pid, portes, fator, expoente, ref=PORTE_BASE):
    """Ordens concluídas de UMA unidade cada, com previsto = porte e observado = previsto × fator × (porte/ref)^expoente."""
    db = db_factory()
    emp = admin.usuario["empresa_id"]
    for i, x in enumerate(portes):
        o = Ordem(empresa_id=emp, unidade_id=unidade_id, numero=f"FAM{pid}-{i:03d}", quantidade=1, produto_id=pid, status="concluida")
        db.add(o)
        db.flush()
        oo = OrdemOperacao(empresa_id=emp, ordem_id=o.id, sequencia=1, etapa_nome="Corpo", nome="Montar", qtd_planejada=1, status="concluida",
                           modulo="montagem", previsto_normal_min=x, fracao_operador=1.0)
        db.add(oo)
        db.flush()
        ini = datetime(2026, 1, 5, 8, tzinfo=timezone.utc) + timedelta(hours=i)
        db.add(Apontamento(empresa_id=emp, unidade_id=unidade_id, ordem_id=o.id, ordem_operacao_id=oo.id, tipo="execucao", inicio=ini,
                           fim=ini + timedelta(minutes=x * fator * (x / ref) ** expoente), quantidade_boa=1, status="aprovado",
                           registrado_por=admin.usuario["id"]))
    db.commit()
    db.close()


def _montagem(p):
    return next(s for s in p["passos"] if s["modulo"] == "montagem")


def _plano_com_parafusos(admin, pid, u, parafusos):
    mb = admin.get(f"/produtos/{pid}/modelo-base").json()
    mb["ligacoes"][0]["fixadores"] = parafusos
    r = admin.post("/planos", {"produto_id": pid, "unidade_id": u, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00", "estrutura": mb})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ o ajuste em si
def test_ajuste_recupera_a_lei_de_escala_e_e_robusto_a_um_ponto_fora():
    portes = [1.5, 2.0, 2.9, 3.8, 5.0, 6.5, 8.0, 10.0]
    pares = [(x, 0.9 * (x / 3.8) ** 0.5) for x in portes]
    f = svc.ajustar_familia(pares)
    assert f.expoente == pytest.approx(0.5, abs=0.01) and f.porte_min == 1.5 and f.porte_max == 10.0
    assert f.fator * (3.8 / f.porte_ref) ** f.expoente == pytest.approx(0.9, abs=0.01)
    ruidoso = pares[:-1] + [(10.0, 3.0)]  # uma ordem que deu errado não derruba a escala (mediana das inclinações)
    assert svc.ajustar_familia(ruidoso).expoente == pytest.approx(0.5, abs=0.12)


def test_sem_tamanhos_diferentes_nao_ha_o_que_aprender():
    assert svc.ajustar_familia([(3.0, 1.1)] * 10) is None                                  # tudo do mesmo tamanho
    assert svc.ajustar_familia([(3.0, 1.1), (3.1, 1.2), (3.05, 1.0), (3.2, 1.1)]) is None  # tamanhos quase iguais
    assert svc.ajustar_familia([(1.0, 1.1), (2.0, 1.2)]) is None                           # só 2 tamanhos


def test_razao_constante_vira_fator_fixo_sem_escala():
    f = svc.ajustar_familia([(x, 1.3) for x in (1.0, 1.5, 2.2, 3.0, 4.5, 6.0)])
    assert f.expoente == 0.0 and f.fator == pytest.approx(1.3)


# ------------------------------------------------------------------ do histórico ao plano
def test_familia_aprende_nos_pedidos_grandes_e_aplica_aos_pequenos(admin, unidade_id, db_factory):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    sem = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 8))
    assert sem["fator_calibracao"] == 1.0
    sem_grande = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 20))

    # 10 pedidos de portes variados (1,5 … 8 min/un): o módulo erra mais quanto maior o pedido
    portes = [1.5, 2.0, 2.5, 3.0, 3.5, 4.5, 5.5, 6.5, 7.2, 8.0]
    _ordens_de_montagem(db_factory, admin, unidade_id, pid, portes, fator=0.8, expoente=0.5)
    r = admin.post("/calibracao/modulos", {"unidade_id": unidade_id, "aplicar": True}).json()
    fam = next(m for m in r["modulos"] if m["produto_id"] == pid and m["modulo"] == "montagem")
    ger = next(m for m in r["modulos"] if m["produto_id"] is None and m["modulo"] == "montagem")
    assert fam["status"] == "sugerido" and fam["expoente"] == pytest.approx(0.5, abs=0.02) and fam["produto_nome"] == "Mesa"
    assert fam["porte_min"] == 1.5 and fam["porte_max"] == 8.0 and ger["expoente"] == 0.0 and r["propostas"] == 2
    props = {(c["produto_id"]): c for c in admin.get("/calibracao/modulos").json()}
    assert "expoente 0.5" in props[pid]["justificativa"] and "dobrar o porte" in props[pid]["justificativa"]

    # pendente não vale
    assert _montagem(_plano_com_parafusos(admin, pid, unidade_id, 8))["fator_calibracao"] == 1.0
    assert admin.post(f"/calibracao/modulos/{props[pid]['id']}/validar", {}).status_code == 200

    pequeno = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 8))     # 2,92 min/un: dentro do que foi observado
    grande = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 20))     # 6,52 min/un
    k_p, k_g = 0.8 * (PORTE_BASE / PORTE_BASE) ** 0.5, 0.8 * ((3 * 0.174 + 20 * 0.30) / PORTE_BASE) ** 0.5
    assert pequeno["fator_calibracao"] == pytest.approx(k_p, abs=0.02)
    assert grande["fator_calibracao"] == pytest.approx(k_g, abs=0.03) and grande["fator_calibracao"] > pequeno["fator_calibracao"]
    assert pequeno["tempo_padrao_min"] == pytest.approx(sem["tempo_padrao_min"] * pequeno["fator_calibracao"], abs=0.02)
    assert grande["tempo_padrao_min"] == pytest.approx(sem_grande["tempo_padrao_min"] * grande["fator_calibracao"], abs=0.03)
    assert grande["previsto_normal_min"] == pytest.approx(sem_grande["previsto_normal_min"])  # a base da calibração não se contamina
    rot = next(c for c in grande["coeficientes"] if c["chave"] == "calibracao:montagem")
    assert rot["status"] == "calibrado" and "família" in rot["fonte"] and "10 amostras" in rot["fonte"]


def test_porte_fora_do_observado_e_rotulado_como_extrapolado_e_o_fator_e_limitado(admin, unidade_id, db_factory):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    _ordens_de_montagem(db_factory, admin, unidade_id, pid, [1.5, 2.0, 2.5, 3.0, 3.5, 4.5, 5.5, 6.5, 7.2, 8.0], fator=0.8, expoente=0.5)
    admin.post("/calibracao/modulos", {"unidade_id": unidade_id, "aplicar": True})
    cid = next(c for c in admin.get("/calibracao/modulos").json() if c["produto_id"] == pid)["id"]
    admin.post(f"/calibracao/modulos/{cid}/validar", {})
    dentro = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 20))
    assert not any("extrapolado" in c["fonte"] for c in dentro["coeficientes"] if c["chave"] == "calibracao:montagem")
    fora = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 60))      # 18,5 min/un: muito além do maior observado (8)
    assert fora["fator_calibracao"] == pytest.approx(0.8 * (12 / PORTE_BASE) ** 0.5, abs=0.03)  # travado na borda: 8 × 1,5 = 12 min/un
    assert any("extrapolado" in c["fonte"] for c in fora["coeficientes"] if c["chave"] == "calibracao:montagem")
    # não cresce sem limite com o tamanho: 200 parafusos dão o mesmo fator que 60
    muito_fora = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 200))
    assert muito_fora["fator_calibracao"] == pytest.approx(fora["fator_calibracao"], abs=0.001)


def test_familia_sem_amostras_suficientes_cai_no_fator_geral_do_modulo(admin, unidade_id, db_factory):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    _ordens_de_montagem(db_factory, admin, unidade_id, pid, [2.0, 3.0, 4.0, 5.0, 6.0], fator=1.5, expoente=0.0)  # 5 < 8 da família
    # outro produto completa as 10 amostras do módulo (o fator geral não separa produtos)
    outro = admin.post("/produtos", {"nome": "Banco"}).json()["id"]
    _ordens_de_montagem(db_factory, admin, unidade_id, outro, [2.0, 3.0, 4.0, 5.0, 6.0], fator=1.5, expoente=0.0)
    r = admin.post("/calibracao/modulos", {"unidade_id": unidade_id, "aplicar": True}).json()
    fam = next(m for m in r["modulos"] if m["produto_id"] == pid)
    assert fam["status"] == "insuficiente" and fam["amostras"] == 5 and fam["minimo"] == 8 and fam["fator_sugerido"] is None
    ger = next(m for m in r["modulos"] if m["produto_id"] is None and m["modulo"] == "montagem")
    assert ger["status"] == "sugerido" and ger["fator_sugerido"] == pytest.approx(1.5)
    admin.post(f"/calibracao/modulos/{next(c for c in admin.get('/calibracao/modulos').json() if c['produto_id'] is None)['id']}/validar", {})
    p = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 8))
    assert p["fator_calibracao"] == pytest.approx(1.5) and "família" not in next(c for c in p["coeficientes"] if c["chave"] == "calibracao:montagem")["fonte"]


def test_familia_validada_tem_precedencia_sobre_o_fator_geral(admin, unidade_id, db_factory):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    _ordens_de_montagem(db_factory, admin, unidade_id, pid, [1.5, 2.0, 2.5, 3.0, 3.5, 4.5, 5.5, 6.5, 7.2, 8.0], fator=1.4, expoente=0.0)
    admin.post("/calibracao/modulos", {"unidade_id": unidade_id, "aplicar": True})
    for c in admin.get("/calibracao/modulos").json():
        admin.post(f"/calibracao/modulos/{c['id']}/validar", {})
    vig = [c for c in admin.get("/calibracao/modulos").json() if c["vigente"]]
    assert {c["produto_id"] for c in vig} == {None, pid}                     # um vigente por chave: geral e da família coexistem
    fam = next(c for c in vig if c["produto_id"] == pid)
    assert fam["expoente"] == 0.0 and fam["fator"] == pytest.approx(1.4)
    p = _montagem(_plano_com_parafusos(admin, pid, unidade_id, 8))
    assert "família" in next(c for c in p["coeficientes"] if c["chave"] == "calibracao:montagem")["fonte"]
    # validar de novo a mesma chave aposenta só a anterior daquela chave
    admin.post("/calibracao/modulos", {"unidade_id": unidade_id, "aplicar": True})
    nova = next(c for c in admin.get("/calibracao/modulos").json() if c["produto_id"] == pid and c["status"] == "pendente")
    admin.post(f"/calibracao/modulos/{nova['id']}/validar", {})
    vig = [c for c in admin.get("/calibracao/modulos").json() if c["vigente"]]
    assert sorted(((c["produto_id"] or 0), c["versao"]) for c in vig) == sorted([(0, 1), (pid, 2)])


def test_migracao_0013_sobe_e_desce_no_sqlite(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    db = tmp_path / "mig.db"
    env = {**os.environ, "ERP_DATABASE_URL": f"sqlite:///{db}"}
    raiz = os.path.dirname(os.path.dirname(__file__))

    def alembic(*args):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=raiz, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]

    def colunas():
        with sqlite3.connect(db) as c:
            return {r[1] for r in c.execute("pragma table_info(calibracoes_modulo)")}

    alembic("upgrade", "0012")
    assert "produto_id" not in colunas()
    alembic("upgrade", "0013")
    assert {"produto_id", "expoente", "porte_ref", "porte_min", "porte_max"} <= colunas()
    alembic("downgrade", "-1")
    assert "produto_id" not in colunas() and "fator" in colunas()
    alembic("upgrade", "head")
