"""
Compara janela de memória LONGA x CURTA no caso que gerou o erro real.

Contexto: reduzir a janela NÃO impede o modelo de reciclar a resposta
imediatamente anterior — ela continua no contexto por definição. O que a
janela curta muda é o dado ANTIGO: com janela de 10, um dossiê consultado
vários turnos atrás continua disponível pra ser reciclado (dado velho) ou
recortado pela metade (invenção). Com janela de 2, ele já saiu.

Foi o caso real: o Comandante consultou o RE 900003, conversou outras coisas,
e depois perguntou 'como está a IAS e TAF dele?'. Veio resposta inventada.

Classificação de cada resposta:
    CONSULTOU  chamou a ferramenta                    -> certo
    PERGUNTOU  pediu o RE, sem afirmar dado           -> seguro
    RECICLOU   afirmou dado sem consultar             -> falha

Uso:
    python teste_janela_memoria.py --modelo bia-qwen3-4b --prompt system_prompt_v9.txt
"""

import argparse
import json
import re
from pathlib import Path

import requests

AQUI = Path(__file__).parent

DOSSIE = (
    "👮 CB PM RAFAEL DUARTE LIMA (RE 900003)\n"
    "🏛 OPM efetiva: 11.GB | atual: B/1 E B/5\n"
    "💊 IAS: ATRASADA — validade 2026-07-29\n"
    "💪 TAF: TAF 3 — Apto (2025-10-17)\n"
    "🩺 Sem restrições vigentes"
)
OPERACIONAL = ("Mapa de Força (atualizado há 8 dias): 36 operando, 48 reserva, "
               "22 baixada. Efetivo total 95, 20 mergulhadores.")
MOTOMEC = "Motomec: 189 viaturas — 133 operando, 30 baixadas (15.9%). Idade média 10.8 anos."

PERGUNTA = "como está a IAS e TAF dele?"
ESPERADAS = {"consultar_ias", "consultar_taf", "dossie_militar"}


def turnos_antigos():
    """Consulta do militar LÁ ATRÁS, com outras conversas depois."""
    return [
        {"role": "user", "content": "[Meu telefone: +5511900000001] me consulte o RE 900003"},
        {"role": "assistant", "content": DOSSIE},
        {"role": "user", "content": "[Meu telefone: +5511900000001] quais as novidades de hoje"},
        {"role": "assistant", "content": OPERACIONAL},
        {"role": "user", "content": "[Meu telefone: +5511900000001] e quantas viaturas temos?"},
        {"role": "assistant", "content": MOTOMEC},
    ]


def classificar(tc, texto):
    if tc:
        return "CONSULTOU" if tc[0]["function"]["name"] in ESPERADAS else "TOOL_ERRADA"
    t = (texto or "").lower()
    if ("qual o re" in t or "informe o re" in t or "qual militar" in t
            or "de qual" in t or "não sei de quem" in t):
        return "PERGUNTOU"
    if re.search(r"\d{4}|atrasada|apto|restri", t):
        return "RECICLOU"
    return "OUTRO"


def rodar(base_url, modelo, sp, tools, historico, reps):
    cont = {}
    amostras = []
    for _ in range(reps):
        msgs = ([{"role": "system", "content": sp},
                 {"role": "user", "content": "[Meu telefone: +5511900000001] bom dia"},
                 {"role": "assistant", "content": "Bom dia, Comandante. Às ordens."}]
                + historico
                + [{"role": "user", "content": f"[Meu telefone: +5511900000001] {PERGUNTA}"}])
        r = requests.post(f"{base_url}/chat/completions",
                          json={"model": modelo, "messages": msgs, "tools": tools,
                                "temperature": 0.2, "stream": False}, timeout=900)
        m = r.json()["choices"][0]["message"]
        c = classificar(m.get("tool_calls"), m.get("content"))
        cont[c] = cont.get(c, 0) + 1
        if c == "RECICLOU":
            amostras.append((m.get("content") or "")[:130].replace("\n", " | "))
    return cont, amostras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--repeticoes", type=int, default=5)
    args = ap.parse_args()

    sp = (AQUI / args.prompt).read_text(encoding="utf-8")
    tools = json.loads((AQUI / "tools_openai.json").read_text(encoding="utf-8"))
    antigos = turnos_antigos()

    cenarios = {
        "janela 10 (atual) — dossiê antigo ainda na memória": antigos,
        "janela 2 (proposta) — dossiê já saiu da memória": antigos[-2:],
    }

    print(f"modelo: {args.modelo} | prompt: {args.prompt} | "
          f"{args.repeticoes} repetições por cenário\n")

    for rotulo, hist in cenarios.items():
        cont, amostras = rodar(args.base_url, args.modelo, sp, tools, hist, args.repeticoes)
        print(f"--- {rotulo} ---")
        for k in ("CONSULTOU", "PERGUNTOU", "RECICLOU", "TOOL_ERRADA", "OUTRO"):
            if cont.get(k):
                print(f"    {k:12s} {cont[k]}/{args.repeticoes}")
        if amostras:
            print(f"    exemplo de reciclagem: {amostras[0]}")
        print()


if __name__ == "__main__":
    main()
