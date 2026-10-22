"""O seed nunca roda sobre um banco que não seja de demonstração."""
import importlib.util
import os
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.integration

RAIZ = Path(__file__).resolve().parents[2]


def _seed():
    spec = importlib.util.spec_from_file_location("seed", RAIZ / "seed" / "gerar_dados_ficticios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _conectar(banco):
    from _env import exigir, opcional
    return psycopg2.connect(host=opcional("PG_HOST", "127.0.0.1"), port=opcional("PG_PORT", "55432"),
                            user=opcional("PG_USER", "admin"), password=exigir("PG_PASS"), dbname=banco)


@pytest.fixture
def banco_descartavel():
    """Cria um banco vazio, entrega o nome e o apaga no fim."""
    adm = _conectar(os.environ.get("PG_DB", "demo_11gb"))
    adm.autocommit = True
    nome = "guarda_seed_teste"
    adm.cursor().execute(f"DROP DATABASE IF EXISTS {nome}")
    adm.cursor().execute(f"CREATE DATABASE {nome}")
    conexoes = []

    def abrir():
        con = _conectar(nome)
        conexoes.append(con)
        return con

    yield abrir
    for con in conexoes:
        con.close()
    adm.cursor().execute(f"DROP DATABASE IF EXISTS {nome}")
    adm.close()


def test_recusa_banco_com_schema_e_sem_marca_de_demo(banco_descartavel):
    con = banco_descartavel()
    con.cursor().execute("CREATE SCHEMA b1; CREATE TABLE b1.efetivo (re int); INSERT INTO b1.efetivo VALUES (1)")
    con.commit()
    with pytest.raises(SystemExit) as e:
        _seed().checar_banco_demo(con.cursor())
    assert "RECUSADO" in str(e.value)
    cur = con.cursor()
    cur.execute("SELECT count(*) FROM b1.efetivo")
    assert cur.fetchone()[0] == 1  # nada foi apagado


def test_aceita_banco_vazio(banco_descartavel):
    _seed().checar_banco_demo(banco_descartavel().cursor())  # não levanta


def test_aceita_banco_ja_marcado_como_demo(banco_descartavel):
    con = banco_descartavel()
    cur = con.cursor()
    cur.execute("CREATE SCHEMA b1; CREATE TABLE b1.efetivo (re int)")
    _seed().marcar_banco_demo(cur)
    _seed().checar_banco_demo(cur)  # não levanta
