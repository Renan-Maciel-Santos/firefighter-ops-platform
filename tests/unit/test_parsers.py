"""Parsers que transformam texto bruto das fontes em dado estruturado."""
from datetime import date

import pytest

from _comum import data_ptbr_para_date, normalizar_posto_grad, re_para_int, texto_ou_none, to_int
from routers.consulta import estacoes_do_municipio, parse_estacao, parse_militar_telefone

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("bruto, esperado", [
    ("900410-3", 900410), ("900295-A", 900295), (" 900001 ", 900001),
    ("nan", None), ("", None), (None, None), ("abc", None),
])
def test_re_com_digito_verificador(bruto, esperado):
    assert re_para_int(bruto) == esperado


def test_celula_vazia_do_pandas_vira_none():
    assert texto_ou_none(float("nan")) is None
    assert to_int("365.0") == 365


def test_data_do_relatorio_ptbr():
    assert data_ptbr_para_date("05/03/2026") == date(2026, 3, 5)
    assert data_ptbr_para_date("2026-03-05") is None


def test_posto_corta_o_sufixo_apos_pm():
    assert normalizar_posto_grad("CB PM - 1C") == "CB PM"
    assert normalizar_posto_grad("1. SGT PM") == "1. SGT PM"


def test_militar_e_telefone_do_mapa_de_forca():
    assert parse_militar_telefone("OLIVEIRA 11900000004") == {"nome": "OLIVEIRA", "telefone": "11900000004"}
    assert parse_militar_telefone("DE LIMA") == {"nome": "DE LIMA", "telefone": None}
    assert parse_militar_telefone(None) == {"nome": None, "telefone": None}


def test_celula_de_estacao_com_codigo_nome_e_telefone():
    r = parse_estacao("990112201\nPB ANA EMILIA\n0000-2201")
    assert r["codigo_opm"] == "990112201"
    assert r["nome"] == "PB ANA EMILIA"
    assert r["telefone_quartel"] == "0000-2201"
    assert r["municipio"] == "Taubaté"


def test_municipio_ignora_acento_e_caixa():
    assert set(estacoes_do_municipio("taubate")) == set(estacoes_do_municipio("Taubaté"))
    assert estacoes_do_municipio("Cidade Inexistente") == []
