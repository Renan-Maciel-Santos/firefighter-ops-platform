"""Configuração comum dos testes.

Os módulos do webapp leem segredos obrigatórios no import (`_env.exigir`).
Para os testes unitários, que não tocam em banco, valores falsos bastam: o
engine do SQLAlchemy é preguiçoso e só conecta na primeira consulta.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for caminho in (RAIZ, os.path.join(RAIZ, "webapp")):
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

# Acima: O .env real (se houver) vem primeiro; os valores falsos só preenchem
# o que faltar, senão os testes de integração conectariam com a senha falsa.
import _env  # noqa: E402,F401  (carrega o .env da raiz)

os.environ.setdefault("PG_PASS", "teste-sem-banco")
os.environ.setdefault("JWT_SECRET_KEY", "chave-so-para-teste-" + "x" * 32)
os.environ.setdefault("N8N_TOKEN", "token-de-teste")
