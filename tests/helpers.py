"""Cenários de teste do fluxo atual: item + peças + ambiente → plano confirmado → ordem."""


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


def montar_ordem(a, unidade_id, *, quantidade=2, prazo=None, cliente="", liberar=False):
    """Ordem de produção pelo caminho real: item e ambiente (criados uma vez por unidade) → plano → confirmar → gerar ordem."""
    if not a.get(f"/espacos?unidade_id={unidade_id}").json():
        _cadastrar_contorno(a, unidade_id)
    produtos = a.get("/produtos").json()
    pid = produtos[0]["id"] if produtos else _mesa(a)[0]
    plano = a.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": quantidade}).json()
    assert a.post(f"/planos/{plano['id']}/confirmar").status_code == 200
    r = a.post(f"/planos/{plano['id']}/gerar-ordem", {"cliente": cliente or None, "prazo": prazo})
    assert r.status_code == 201, r.text
    if liberar:
        assert a.post(f"/ordens/{r.json()['id']}/liberar").status_code == 200
    return a.get(f"/ordens/{r.json()['id']}").json()
