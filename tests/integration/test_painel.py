"""O painel abre com dados e respeita a regra de acesso."""
import pytest

pytestmark = pytest.mark.integration

ROTAS_DAS_ABAS = [
    "/pessoal/resumo", "/pessoal/qpo-lotacao", "/pessoal/operacional", "/pessoal/forca-operacional",
    "/pessoal/afastamentos", "/pessoal/realocacao", "/saude/resumo", "/saude/restricoes",
    "/taf/resumo", "/taf/situacao", "/mapa-forca/resumo", "/mapa-forca/estacoes", "/mapa-forca/linhas",
    "/ocorrencias/resumo", "/ocorrencias/serie-mensal", "/ocorrencias/tempo-resposta-anual",
    "/auditoria-cobom/itens", "/eap/turmas", "/eap/pendentes", "/elogios/resumo", "/sjd/resumo",
    "/viaturas/", "/viaturas/resumo", "/uge/resumo", "/ppmq/taxa-baixadas", "/ppmq/idade-media",
    "/etl-status/", "/usuarios",
]


@pytest.mark.parametrize("rota", ROTAS_DAS_ABAS)
def test_rotas_das_abas_respondem_com_dados(admin, rota):
    status, corpo = admin.get(rota)
    assert status == 200, corpo
    assert corpo, f"{rota} veio vazio"


def test_efetivo_do_seed_bate_com_o_qpo(admin):
    _, r = admin.get("/pessoal/resumo")
    assert 400 <= r["existente_total"] <= 600
    assert r["vagas_totais"] >= r["existente_total"]


def test_ppmq_total_cobre_os_quatro_sgbs(admin):
    _, r = admin.get("/ppmq/taxa-baixadas")
    linhas = {linha["sgb"]: linha for linha in r["data"]}
    total = linhas.pop("11º GB")
    assert len(linhas) == 4
    assert total["baixadas"] >= sum(linha["baixadas"] for linha in linhas.values())


def test_praca_so_ve_a_aba_da_propria_secao(praca_b4):
    _, me = praca_b4.get("/auth/me")
    assert me["abas"] == ["viaturas"]
    assert praca_b4.get("/viaturas/resumo")[0] == 200
    for rota in ("/pessoal/resumo", "/saude/resumo", "/usuarios", "/sjd/resumo"):
        assert praca_b4.get(rota)[0] == 403, rota


def test_sem_login_nao_entra(anonimo):
    assert anonimo.get("/pessoal/resumo")[0] == 401
