"""As medidas do pedido dimensionam as peças: o tempo padrão acompanha o tamanho (contas conferidas à mão)."""
import pytest

from app.services.formulas import FaltaValor, FormulaErro, avaliar, campos_usados, compilar
from tests.conftest import registrar
from tests.test_plano import _cadastrar_contorno

FT = 1 / 0.91  # tolerâncias: pessoal 5 % + fadiga básica 4 %
CAMPOS = [{"nome": "Largura", "tipo": "numero", "unidade": "cm", "obrigatorio": True},
          {"nome": "Profundidade", "tipo": "numero", "unidade": "cm"},
          {"nome": "Tipo", "tipo": "opcao", "opcoes": ["Simples", "Reforçada"]}]


def _ev(texto, **v):
    return avaliar(compilar(texto), v)


# ------------------------------------------------------------------ o interpretador
@pytest.mark.parametrize("texto,v,esperado", [
    ("{Altura}", {"altura": 0.6}, 0.6),
    ("{Largura} - 0.036", {"largura": 0.3}, 0.264),
    ("2 + 3 * 4", {}, 14),
    ("(2 + 3) * 4", {}, 20),
    ("-{A} * 2", {"a": 3}, -6),
    ("10 / 4", {}, 2.5),
    ('se({Tipo} == "reforçada"; 2; 1)', {"tipo": "Reforçada"}, 2),        # texto compara sem diferenciar maiúscula
    ('se({Tipo} != "Simples"; 2; 1)', {"tipo": "Simples"}, 1),
    ("se({L} > 0.6; 4; 2)", {"l": 0.61}, 4),
    ("teto({L} * 10)", {"l": 0.61}, 7),
    ("piso(2.9)", {}, 2),
    ("arred(2.345; 2)", {}, 2.35),
    ("max(1; 5; 3)", {}, 5),
    ("min({A}; {B})", {"a": 4, "b": 2}, 2),
    ("abs(-3)", {}, 3),
])
def test_interpretador_calcula(texto, v, esperado):
    assert _ev(texto, **v) == pytest.approx(esperado)


@pytest.mark.parametrize("texto", [
    "1,5", "max(1,2)", "2 / 0", "foo(1)", '__import__("os")', "(1", "1 2", "", "se(1; 2; 3)", "min(1)", "{A} + \"x\"",
    "9" * 300, "1 +", "()", "{}", "a.b", "1; 2", "se({A} > 1; 2)", "arred(1; 9)", "2 ** 3", "{A} == \"x\"",
])
def test_interpretador_recusa_o_que_nao_entende(texto):
    with pytest.raises(FormulaErro):
        _ev(texto, a=1)


def test_campo_sem_valor_e_erro_especifico_e_variaveis_sao_listadas():
    with pytest.raises(FaltaValor) as e:
        _ev("{Largura} * 2")
    assert e.value.campo == "Largura"
    assert campos_usados(compilar('se({Tipo} == "x"; {Largura}; {Altura} + 1)')) == {"tipo", "largura", "altura"}


def test_so_avalia_o_ramo_escolhido():
    assert _ev("se(1 > 0; 5; {Inexistente})") == 5               # o ramo não escolhido não é avaliado
    with pytest.raises(FormulaErro):
        _ev("1e400")                                              # notação científica não existe
    with pytest.raises(FormulaErro):
        _ev("999999999 * 999999999")                              # estouro do limite


def test_aninhamento_excessivo_e_recusado():
    with pytest.raises(FormulaErro):
        compilar("(" * 40 + "1" + ")" * 40)


# ------------------------------------------------------------------ produto com fórmulas
def _mesa_parametrica(a, u, *, formulas=True, peso_fixo=False, parafusos="teto({Largura} * 10)"):
    _cadastrar_contorno(a, u)
    p = a.post("/produtos", {"nome": "Mesa"}).json()["id"]
    assert a.patch(f"/produtos/{p}", {"campos_especificacao": CAMPOS}).status_code == 200
    f = (lambda **kw: kw) if formulas else (lambda **kw: {})
    tampo = a.post(f"/produtos/{p}/componentes", {"nome": "Tampo", "quantidade": 1, "material": "mdf", "espessura_m": 0.02,
                                                   "comprimento_m": 1.0, "largura_m": 0.5, **({"peso_kg": 7} if peso_fixo else {}),
                                                   "formulas": f(comprimento_m="{Largura}", largura_m="{Profundidade}")})
    assert tampo.status_code == 201, tampo.text
    lat = a.post(f"/produtos/{p}/componentes", {"nome": "Lateral", "quantidade": 2, "material": "mdf", "espessura_m": 0.02,
                                                 "comprimento_m": 0.7, "largura_m": 0.5, "formulas": f(largura_m="{Profundidade}")})
    assert lat.status_code == 201, lat.text
    lig = a.post(f"/produtos/{p}/ligacoes", {"componente_id": lat.json()["id"], "ligado_a_id": tampo.json()["id"], "metodo": "parafuso",
                                             "fixadores": 8, "formula_fixadores": parafusos if formulas else ""})
    assert lig.status_code == 201, lig.text
    return p


def _plano(a, p, u, espec, **kw):
    return a.post("/planos", {"produto_id": p, "unidade_id": u, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00", "especificacoes": espec, **kw})


def _passo(plano, modulo):
    return next(s for s in plano["passos"] if s["modulo"] == modulo)


def test_tempo_padrao_acompanha_o_tamanho_do_pedido(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    grande = _plano(admin, p, unidade_id, {"Largura": 100, "Profundidade": 50}).json()
    pequena = _plano(admin, p, unidade_id, {"Largura": 60, "Profundidade": 40}).json()
    # corte (perímetros × peças × 2 un): 100×50 → 6,0 + 9,6 = 15,6 m ; 60×40 → 4,0 + 8,8 = 12,8 m, a 30 m/min
    assert _passo(grande, "corte")["parametros_modulo"]["metros_de_corte"] == 15.6
    assert _passo(pequena, "corte")["parametros_modulo"]["metros_de_corte"] == 12.8
    assert _passo(grande, "corte")["tempo_exec_min"] == pytest.approx(15.6 / 30, abs=0.01)  # tempo de máquina: sem tolerância
    assert _passo(pequena, "corte")["tempo_exec_min"] == pytest.approx(12.8 / 30, abs=0.01)
    # montagem: (3 peças × 0,174 + parafusos × 0,30) × 2 un; parafusos = teto(Largura em m × 10) = 10 e 6
    assert _passo(grande, "montagem")["tempo_padrao_min"] == pytest.approx((3 * 0.174 + 10 * 0.30) * 2 * FT, abs=0.01)
    assert _passo(pequena, "montagem")["tempo_padrao_min"] == pytest.approx((3 * 0.174 + 6 * 0.30) * 2 * FT, abs=0.01)
    assert pequena["totais"]["tempo_padrao_min"] < grande["totais"]["tempo_padrao_min"]
    # as peças usadas ficam guardadas no plano (auditável) e o produto continua com os valores de partida
    est = admin.get(f"/planos/{pequena['id']}").json()["estrutura"]
    tampo = next(c for c in est["componentes"] if c["nome"] == "Tampo")
    assert tampo["comprimento_m"] == 0.6 and tampo["largura_m"] == 0.4 and tampo["formulas"]["comprimento_m"] == "{Largura}"
    assert est["ligacoes"][0]["fixadores"] == 6
    assert admin.get(f"/produtos/{p}/modelo-base").json()["componentes"][0]["comprimento_m"] == 1.0


def test_peso_acompanha_as_medidas_e_peso_fixo_e_desconsiderado(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id, peso_fixo=True)
    pl = _plano(admin, p, unidade_id, {"Largura": 60, "Profundidade": 40}).json()
    tampo = next(c for c in admin.get(f"/planos/{pl['id']}").json()["estrutura"]["componentes"] if c["nome"] == "Tampo")
    assert tampo["peso_kg"] is None                                          # não ficou os 7 kg do tamanho grande
    assert any("peso fixo de «Tampo» foi desconsiderado" in x for x in pl["premissas"])
    assert any("estimado" in x and "Tampo" in x for x in pl["premissas"])   # e o sistema estimou pelas novas medidas (rotulado)


def test_medida_sem_ligacao_com_as_pecas_gera_aviso_e_com_ligacao_nao(admin, unidade_id):
    solto = _mesa_parametrica(admin, unidade_id, formulas=False)
    pl = _plano(admin, solto, unidade_id, {"Largura": 60, "Profundidade": 40}).json()
    assert any("NÃO muda com o tamanho" in x and "Largura, Profundidade" in x for x in pl["premissas"])
    # sem as fórmulas, o tempo é igual para qualquer tamanho: é exatamente o risco que o aviso denuncia
    outro = _plano(admin, solto, unidade_id, {"Largura": 200, "Profundidade": 90}).json()
    assert outro["totais"]["tempo_padrao_min"] == pl["totais"]["tempo_padrao_min"]


def test_medida_ligada_as_pecas_nao_gera_aviso(client):
    a = registrar(client, "Empresa Param")
    p = _mesa_parametrica(a, a.unidade_id)
    pl = _plano(a, p, a.unidade_id, {"Largura": 60, "Profundidade": 40}).json()
    assert not any("NÃO muda" in x for x in pl["premissas"])


def test_previa_calcula_as_pecas_e_lista_o_que_ainda_depende_de_campo_vazio(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    r = admin.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 60}})          # Profundidade ainda vazia
    assert r.status_code == 200, r.text
    d = r.json()
    tampo = next(c for c in d["estrutura"]["componentes"] if c["nome"] == "Tampo")
    assert tampo["comprimento_m"] == 0.6 and tampo["largura_m"] == 0.5               # largura_m depende de Profundidade: fica o valor de partida
    assert d["estrutura"]["ligacoes"][0]["fixadores"] == 6 and d["usa_formulas"] is True
    assert {(x["campo"], x["falta"]) for x in d["pendentes"]} == {("largura_m", "Profundidade")}
    # gerar o plano de verdade exige o campo que a fórmula usa
    r = _plano(admin, p, unidade_id, {"Largura": 60})
    assert r.status_code == 422 and "Profundidade" in r.json()["detail"]


def test_resultado_impossivel_e_recusado_dizendo_qual_peca(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    pid = admin.get(f"/produtos/{p}/estrutura").json()["componentes"][1]["id"]            # Lateral
    assert admin.patch(f"/produtos/{p}/componentes/{pid}", {"formulas": {"comprimento_m": "{Largura} - 1"}}).status_code == 200
    r = _plano(admin, p, unidade_id, {"Largura": 80, "Profundidade": 40})                 # 0,8 − 1 = −0,2 m
    assert r.status_code == 422
    d = r.json()["detail"]
    assert "Lateral" in d and "comprimento_m" in d and "-0.2" in d


@pytest.mark.parametrize("formula,trecho", [
    ("{Altura} * 2", "não tem o campo"),
    ("{Largura} +", "Fórmula de"),
    ("max(1, 2)", "ponto e vírgula"),
    ("foo({Largura})", "desconhecida"),
])
def test_formula_invalida_e_recusada_ao_salvar(admin, unidade_id, formula, trecho):
    p = _mesa_parametrica(admin, unidade_id)
    cid = admin.get(f"/produtos/{p}/estrutura").json()["componentes"][0]["id"]
    r = admin.patch(f"/produtos/{p}/componentes/{cid}", {"formulas": {"comprimento_m": formula}})
    assert r.status_code == 422 and trecho in r.json()["detail"]
    r = admin.post(f"/produtos/{p}/componentes", {"nome": "Novo", "formulas": {"comprimento_m": formula}})
    assert r.status_code == 422


def test_so_campos_numericos_da_peca_aceitam_formula(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    cid = admin.get(f"/produtos/{p}/estrutura").json()["componentes"][0]["id"]
    assert admin.patch(f"/produtos/{p}/componentes/{cid}", {"formulas": {"nome": "{Largura}"}}).status_code == 422
    assert admin.patch(f"/produtos/{p}/componentes/{cid}", {"formulas": {"material": "{Largura}"}}).status_code == 422
    lid = admin.get(f"/produtos/{p}/estrutura").json()["ligacoes"][0]
    assert lid["formula_fixadores"] == "teto({Largura} * 10)"
    r = admin.post(f"/produtos/{p}/ligacoes", {"componente_id": cid, "metodo": "cola", "formula_fixadores": "{Inexistente}"})
    assert r.status_code == 422


def test_ajuste_manual_sobre_uma_formula_fica_registrado(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    montada = admin.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 60, "Profundidade": 40}}).json()["estrutura"]
    tampo = next(c for c in montada["componentes"] if c["nome"] == "Tampo")
    tampo["comprimento_m"] = 0.65                                          # a pessoa corrigiu à mão (ex.: sobra de aparo)
    r = _plano(admin, p, unidade_id, {"Largura": 60, "Profundidade": 40}, estrutura=montada)
    assert r.status_code == 201, r.text
    pl = r.json()
    assert any("Ajuste manual" in x and "Tampo" in x and "0.65" in x and "0.6" in x for x in pl["premissas"])
    assert next(c for c in admin.get(f"/planos/{pl['id']}").json()["estrutura"]["componentes"] if c["nome"] == "Tampo")["comprimento_m"] == 0.65
    # a estrutura enviada IGUAL à calculada não gera ajuste
    limpa = _plano(admin, p, unidade_id, {"Largura": 60, "Profundidade": 40},
                   estrutura=admin.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 60, "Profundidade": 40}}).json()["estrutura"]).json()
    assert not any("Ajuste manual" in x for x in limpa["premissas"])


def test_recalcular_com_medidas_novas_recalcula_as_pecas_e_sem_mudanca_mantem_o_ajuste(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    montada = admin.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 100, "Profundidade": 50}}).json()["estrutura"]
    next(c for c in montada["componentes"] if c["nome"] == "Lateral")["quantidade"] = 4           # ajuste manual: 4 laterais
    pl = _plano(admin, p, unidade_id, {"Largura": 100, "Profundidade": 50}, estrutura=montada).json()
    base = {"produto_id": p, "unidade_id": unidade_id, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00"}
    # mesmas medidas, sem estrutura nova: o ajuste continua
    mesmo = admin.post(f"/planos/{pl['id']}/recalcular", {**base, "especificacoes": {"Largura": 100, "Profundidade": 50}}).json()
    assert next(c for c in admin.get(f"/planos/{pl['id']}").json()["estrutura"]["componentes"] if c["nome"] == "Lateral")["quantidade"] == 4
    assert mesmo["totais"]["tempo_padrao_min"] == pl["totais"]["tempo_padrao_min"]
    # medidas novas, sem estrutura nova: as peças são RECALCULADAS (não reaproveita peça velha do tamanho antigo)
    novo = admin.post(f"/planos/{pl['id']}/recalcular", {**base, "especificacoes": {"Largura": 60, "Profundidade": 40}}).json()
    est = admin.get(f"/planos/{pl['id']}").json()["estrutura"]
    assert next(c for c in est["componentes"] if c["nome"] == "Tampo")["comprimento_m"] == 0.6
    assert next(c for c in est["componentes"] if c["nome"] == "Lateral")["quantidade"] == 2
    assert _passo(novo, "corte")["parametros_modulo"]["metros_de_corte"] == 12.8


def test_arranjo_e_plano_do_arranjo_usam_as_pecas_calculadas(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    corpo = {"produto_id": p, "unidade_id": unidade_id, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00"}
    peq = admin.post("/planos/arranjos", {**corpo, "especificacoes": {"Largura": 60, "Profundidade": 40}})
    gra = admin.post("/planos/arranjos", {**corpo, "especificacoes": {"Largura": 200, "Profundidade": 90}})
    assert peq.status_code == 200 and gra.status_code == 200, (peq.text, gra.text)
    assert peq.json()["candidatos"][0]["makespan_min"] < gra.json()["candidatos"][0]["makespan_min"]
    c = peq.json()["candidatos"][0]
    r = admin.post("/planos/de-arranjo", {**corpo, "especificacoes": {"Largura": 60, "Profundidade": 40},
                                          "escolha": {"pessoas": c["pessoas"], "lotes": c["lotes"], "regra": c["regra"], "meio_id": c["meio_id"]}})
    assert r.status_code == 201, r.text
    assert next(c for c in admin.get(f"/planos/{r.json()['id']}").json()["estrutura"]["componentes"] if c["nome"] == "Tampo")["comprimento_m"] == 0.6


def test_opcao_do_pedido_pode_decidir_a_quantidade_de_pecas(admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    cid = admin.get(f"/produtos/{p}/estrutura").json()["componentes"][1]["id"]
    assert admin.patch(f"/produtos/{p}/componentes/{cid}", {"formulas": {"quantidade": 'se({Tipo} == "Reforçada"; 4; 2)'}}).status_code == 200
    simples = admin.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 60, "Tipo": "Simples"}}).json()["estrutura"]
    forte = admin.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 60, "Tipo": "Reforçada"}}).json()["estrutura"]
    assert next(c for c in simples["componentes"] if c["nome"] == "Lateral")["quantidade"] == 2
    assert next(c for c in forte["componentes"] if c["nome"] == "Lateral")["quantidade"] == 4


def test_formulas_respeitam_a_empresa(client, admin, unidade_id):
    p = _mesa_parametrica(admin, unidade_id)
    outra = registrar(client, "Empresa B")
    assert outra.post(f"/produtos/{p}/montar", {"especificacoes": {"Largura": 60}}).status_code == 404
