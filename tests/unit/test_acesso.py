"""A regra de acesso é a fonte única do painel: o backend nega, o frontend só esconde."""
import pytest

from acesso import ABAS, ABAS_SO_ADMIN, SECAO_ABAS, abas_do_usuario

pytestmark = pytest.mark.unit


def test_admin_ve_tudo():
    assert abas_do_usuario("admin", None) == ABAS


def test_oficial_ve_tudo_menos_gestao_de_usuarios():
    abas = abas_do_usuario("oficial", None)
    assert set(abas) == set(ABAS) - set(ABAS_SO_ADMIN)
    assert "usuarios" not in abas


@pytest.mark.parametrize("secao", list(SECAO_ABAS))
def test_praca_ve_so_a_propria_secao(secao):
    assert abas_do_usuario("praca", secao) == tuple(SECAO_ABAS[secao])


def test_praca_sem_secao_nao_ve_nada():
    # Estado inválido não pode virar acesso amplo por omissão.
    assert abas_do_usuario("praca", None) == ()
    assert abas_do_usuario("praca", "Seção inexistente") == ()


@pytest.mark.parametrize("perfil", ["comando", "administrativo", "operacional", "", "ADMIN"])
def test_perfil_desconhecido_nega_por_omissao(perfil):
    assert abas_do_usuario(perfil, "B/4") == ()


def test_toda_aba_de_secao_existe_no_painel():
    for abas in SECAO_ABAS.values():
        assert set(abas) <= set(ABAS)
