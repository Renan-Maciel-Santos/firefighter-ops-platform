"""Fixtures dos testes de integração.

Rodam contra a stack da demonstração no ar (docker compose up + seed). Se ela
não estiver de pé, os testes FALHAM em vez de pular: um CI sem a stack não
pode passar por engano.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

BASE = os.environ.get("DEMO_URL", "http://127.0.0.1:8800")
SENHA = os.environ.get("DEMO_SENHA", "demo1234")


class Api:
    def __init__(self, token=None, api_token=None):
        self.token, self.api_token = token, api_token

    def req(self, metodo, rota, corpo=None, **params):
        url = BASE + rota + ("?" + urllib.parse.urlencode(params) if params else "")
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        if self.api_token:
            h["X-API-Token"] = self.api_token
        dados = json.dumps(corpo).encode() if corpo is not None else None
        r = urllib.request.Request(url, data=dados, headers=h, method=metodo)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def get(self, rota, **params):
        return self.req("GET", rota, **params)


def login(matricula):
    status, corpo = Api().req("POST", "/auth/login", {"matricula": matricula, "senha": SENHA})
    assert status == 200, f"login de {matricula} falhou ({status}): a stack e o seed estão no ar?"
    return Api(token=corpo["access_token"])


@pytest.fixture(scope="session")
def anonimo():
    return Api()


@pytest.fixture(scope="session")
def admin():
    return login("900003")


@pytest.fixture(scope="session")
def praca_b4():
    return login("demo.b4")


@pytest.fixture(scope="session")
def bia():
    tok = os.environ.get("N8N_TOKEN")
    if not tok:
        from _env import exigir
        tok = exigir("N8N_TOKEN")
    return Api(api_token=tok)
