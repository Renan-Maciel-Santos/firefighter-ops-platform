"""Ferramentas da B.I.A.: token próprio e mensagem pronta para o WhatsApp."""
import pytest

from conftest import Api

pytestmark = pytest.mark.integration


def test_ferramentas_exigem_o_token_do_n8n(anonimo):
    assert anonimo.get("/consulta/efetivo")[0] == 401
    assert Api(api_token="errado").get("/consulta/efetivo")[0] == 401


def test_remetente_autorizado_e_cumprimentado(bia):
    status, r = bia.get("/consulta/identificar", telefone="5511900000001")
    assert status == 200
    assert r["mensagem"] == "Às ordens, Cb Duarte."


def test_mensagem_traz_os_numeros_do_banco(bia, admin):
    # O agente só repassa "mensagem": os números precisam ser os do banco.
    _, r = bia.get("/consulta/efetivo-por-lotacao")
    _, resumo = admin.get("/pessoal/resumo")
    assert f"({resumo['existente_total']} ativos)" in r["mensagem"]


@pytest.mark.parametrize("rota, params", [
    ("/consulta/militar", {"re": "900044"}),
    ("/consulta/ias", {"re": "900092"}),
    ("/consulta/taf", {"re": "900010"}),
    ("/consulta/restricoes", {"re": "900010"}),
    ("/consulta/guarnicao", {"municipio": "Taubaté"}),
    ("/consulta/resumo-operacional", {}),
    ("/consulta/motomec-resumo", {}),
    ("/consulta/uge-resumo", {}),
    ("/consulta/elogios-resumo", {}),
])
def test_ferramentas_devolvem_mensagem(bia, rota, params):
    status, r = bia.get(rota, **params)
    assert status == 200, r
    assert r["mensagem"].strip()


def test_re_inexistente_e_404_e_nao_resposta_inventada(bia):
    assert bia.get("/consulta/militar", re="123456")[0] == 404
