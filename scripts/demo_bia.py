"""
Demonstração da camada de ferramentas da B.I.A. (assistente de WhatsApp).

Em produção, o n8n recebe a mensagem do WhatsApp, o LLM escolhe a ferramenta
e chama um endpoint /consulta/* do webapp. O endpoint devolve o campo
"mensagem" JÁ FORMATADO, e o modelo é instruído a repassá-lo literalmente:
nenhum número da resposta passa pelo modelo.

Este script faz as mesmas chamadas que o agente faria para perguntas típicas
do comando e imprime o que iria para o WhatsApp. Não usa LLM nem n8n.

    python scripts/demo_bia.py [--url http://127.0.0.1:8800]

Lê N8N_TOKEN do ambiente ou do .env da raiz.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

# (pergunta do usuário no WhatsApp, ferramenta que o agente chama, parâmetros)
CONVERSA = [
    ("bom dia", "/consulta/identificar", {"telefone": "5511900000010"}),
    ("como está o efetivo hoje?", "/consulta/efetivo", {}),
    ("e o mapa de força?", "/consulta/resumo-operacional", {}),
    ("quem está de serviço no PB Sul?", "/consulta/guarnicao", {"estacao": "PB SUL"}),
    ("me consulte o RE 900044", "/consulta/militar", {"re": "900044"}),
    ("a IAS dele está em dia?", "/consulta/ias", {"re": "900044"}),
    ("quantas viaturas baixadas?", "/consulta/motomec-resumo", {}),
    ("algum processo da UGE vencido?", "/consulta/uge-vencidos", {}),
]


def token():
    if os.environ.get("N8N_TOKEN"):
        return os.environ["N8N_TOKEN"]
    from _env import exigir
    return exigir("N8N_TOKEN", "Defina N8N_TOKEN no .env (o webapp precisa do mesmo valor).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8800")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    tok = token()

    print("=" * 68)
    print("  B.I.A. — respostas que o agente repassa no WhatsApp (dados fictícios)")
    print("=" * 68)
    for i, (pergunta, rota, params) in enumerate(CONVERSA, 1):
        url = a.url + rota + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"X-API-Token": tok})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30) as r:
            corpo = json.loads(r.read())
        ms = (time.perf_counter() - t0) * 1000
        mensagem = corpo.get("mensagem") or json.dumps(corpo, ensure_ascii=False)[:300]
        print(f"\n--- {i}/{len(CONVERSA)} " + "-" * 50)
        print(f"Comandante: {pergunta}")
        print(f"   tool  → GET {rota} {params or ''}  ({ms:.0f} ms)")
        print("B.I.A.:     " + mensagem.replace("\n", "\n            "))


if __name__ == "__main__":
    main()
