"""Geração da Ordem de Serviço do EAP a partir do modelo .docx."""
import io
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import docx
import pytest

import eap_documento as doc

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[2]
MODELO = RAIZ / "webapp" / "modelos" / "eap_os_modelo.docx"


@pytest.fixture(scope="module")
def modelo() -> bytes:
    if not MODELO.exists():
        subprocess.run([sys.executable, str(MODELO.parent / "gerar_modelo_padrao.py")], check=True)
    return MODELO.read_bytes()


def _texto(conteudo: bytes) -> str:
    return "\n".join(p.text for p in docx.Document(io.BytesIO(conteudo)).paragraphs)


def test_modelo_padrao_tem_os_campos_obrigatorios(modelo):
    assert set(doc.OBRIGATORIOS) <= doc.campos_do_modelo(modelo)


def test_gerar_preenche_campos_e_um_paragrafo_por_militar(modelo):
    militares = [doc.linha_militar("CB PM", 900010, "7", "LEANDRO CASTRO DA SILVA"),
                 doc.linha_militar("1. SGT PM", 900020, None, "ANA DE SOUZA")]
    campos = {"numero": "007", "ano": "2026", "periodo_ead": "01FEV27 a 16MAR27",
              "data_extenso": "20 de outubro de 2026", "destinatarios": "1º SGB",
              "assunto": "EAP 2027 Turma I", "publico_pracas": "Cb/Sd PM",
              "presencial_pracas": "190800NOV26", "local_pracas": "Local fictício",
              "assinante_nome": "FULANO DE TAL", "assinante_funcao": "Cmt"}
    texto = _texto(doc.gerar(modelo, campos, militares, tem_pracas=True, tem_oficiais=False))

    assert "EAP-007/2026" in texto
    assert "Cb PM 900010-7 Leandro Castro da Silva" in texto
    assert "1º Sgt PM 900020 Ana de Souza" in texto
    assert "{{" not in texto  # nenhum campo sobrou
    assert "OFICIAIS:" not in texto  # parágrafo condicional de oficiais removido


def test_formatos_de_data_militares():
    assert doc.data_extenso(date(2026, 10, 9)) == "9 de outubro de 2026"
    assert doc.data_militar(date(2026, 10, 26)) == "26OUT26"
    assert doc.dtg(datetime(2026, 11, 19, 8, 0)) == "190800NOV26"


@pytest.mark.parametrize("cod, esperado", [
    (990111201, "1º SGB"),
    (990113900, "SAT"),      # NAT de SGB pertence à SAT, não ao SGB onde fica
    (990119200, "SAT"),
    (990119131, "COBOM"),
    (990119110, "SAdm"),
    (None, None),
    (123450000, None),       # OPM de fora da unidade
])
def test_destinatario_por_opm(cod, esperado):
    assert doc.destinatario(cod) == esperado


def test_destinatarios_em_ordem_e_sem_repeticao():
    cods = [990119131, 990112101, 990111201, 990112202, None]
    assert doc.texto_destinatarios(cods) == "1º SGB, 2º SGB e COBOM"
