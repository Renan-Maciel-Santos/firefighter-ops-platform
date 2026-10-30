"""Tokens de sessão: o que o painel emite volta íntegro, e o resto é recusado.

O get_current_user consulta o banco depois de validar o token, então o caso
válido decodifica direto com a mesma chave e algoritmo do módulo. Os casos
recusados passam pelo get_current_user de verdade: a recusa acontece antes de
qualquer consulta, por isso db=None basta.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from routers.auth import ALGORITHM, SECRET_KEY, create_access_token, get_current_user

pytestmark = pytest.mark.unit


def _recusado(token):
    with pytest.raises(HTTPException) as exc:
        get_current_user(token=token, db=None)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("matricula", ["900003", "demo.b1"])
def test_token_emitido_volta_com_a_mesma_matricula(matricula):
    token = create_access_token({"sub": matricula, "perfil": "admin"})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == matricula


def test_token_expirado_e_recusado():
    vencido = datetime.now(timezone.utc) - timedelta(minutes=1)
    _recusado(jwt.encode({"sub": "900003", "exp": vencido}, SECRET_KEY, algorithm=ALGORITHM))


def test_token_assinado_com_outra_chave_e_recusado():
    _recusado(jwt.encode({"sub": "900003"}, "outra-chave-" + "y" * 32, algorithm=ALGORITHM))


def test_token_sem_assinatura_alg_none_e_recusado():
    _recusado(jwt.encode({"sub": "900003"}, None, algorithm="none"))


def test_sub_numerico_e_recusado():
    # O PyJWT exige que o sub seja texto. A matrícula sai do banco como texto,
    # então o login nunca emite sub numérico; o teste documenta a exigência.
    _recusado(jwt.encode({"sub": 900003}, SECRET_KEY, algorithm=ALGORITHM))
