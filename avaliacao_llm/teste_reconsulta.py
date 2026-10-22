"""
Testa se o modelo RECONSULTA quando o dado já está no histórico da conversa.

Reproduzido em 11/08/2026 (execução 1584 + reprodução 6/6): com o resultado de
uma consulta anterior na memória, o modelo respondia SEM chamar ferramenta,
recortando o histórico. Quando o histórico estava íntegro a resposta saía
certa (porém velha); quando estava parcial, ele preenchia inventando.

O caso real que o Comandante recebeu:
    Elogios: 2024 — 2025
    TAF: 2024 — 2025
    IAS: Atualizado há 3 dias — 2024 — 2025 (sem restrições)

Sucesso aqui = CHAMAR A FERRAMENTA. Responder certo a partir da memória
continua sendo falha: o dado é do instante da consulta anterior.

Uso:
    python teste_reconsulta.py --modelo bia-qwen3-4b --prompt system_prompt_v10.txt
"""

import argparse
import json
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

# (pergunta de acompanhamento, ferramentas aceitáveis)
CASOS = [
    ("como está a IAS e TAF dele?", {"consultar_ias", "consultar_taf", "dossie_militar"}),
    ("e a IAS dele?", {"consultar_ias", "dossie_militar"}),
    ("e o TAF?", {"consultar_taf", "dossie_militar"}),
    ("ele tem restrição?", {"consultar_restricoes", "dossie_militar", "listar_com_restricao"}),
    ("confirma a validade da IAS dele?", {"consultar_ias", "dossie_militar"}),
    ("quantos elogios ele tem?", {"consultar_elogios_militar", "dossie_militar"}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--repeticoes", type=int, default=3)
    args = ap.parse_args()

    sp = (AQUI / args.prompt).read_text(encoding="utf-8")
    tools = json.loads((AQUI / "tools_openai.json").read_text(encoding="utf-8"))

    print(f"modelo: {args.modelo} | prompt: {args.prompt} | "
          f"{len(CASOS)} casos x {args.repeticoes} repetições\n")

    consultou = reciclou = errado = 0
    amostras = []

    for pergunta, esperadas in CASOS:
        marcas = []
        for _ in range(args.repeticoes):
            msgs = [
                {"role": "system", "content": sp},
                {"role": "user", "content": "[Meu telefone: +5511900000001] bom dia"},
                {"role": "assistant", "content": "Bom dia, Comandante. Às ordens."},
                {"role": "user", "content": "[Meu telefone: +5511900000001] me consulte o RE 900003"},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "t1", "type": "function",
                                 "function": {"name": "dossie_militar",
                                              "arguments": '{"re":"900003"}'}}]},
                {"role": "tool", "tool_call_id": "t1",
                 "content": json.dumps({"mensagem": DOSSIE}, ensure_ascii=False)},
                {"role": "assistant", "content": DOSSIE},
                {"role": "user", "content": f"[Meu telefone: +5511900000001] {pergunta}"},
            ]
            r = requests.post(f"{args.base_url}/chat/completions",
                              json={"model": args.modelo, "messages": msgs,
                                    "tools": tools, "temperature": 0.2,
                                    "stream": False}, timeout=900)
            m = r.json()["choices"][0]["message"]
            tc = m.get("tool_calls")
            if tc and tc[0]["function"]["name"] in esperadas:
                marcas.append("."); consultou += 1
            elif tc:
                marcas.append("x"); errado += 1
            else:
                marcas.append("R"); reciclou += 1
                amostras.append((pergunta, (m.get("content") or "")[:120].replace("\n", " | ")))
        print(f"  [{''.join(marcas)}] {pergunta}")

    total = len(CASOS) * args.repeticoes
    print(f"\n{'='*62}")
    print("legenda: . = reconsultou (certo) | x = ferramenta errada | R = reciclou o histórico")
    print(f"  RECONSULTOU        : {consultou}/{total}")
    print(f"  reciclou histórico : {reciclou}/{total}")
    print(f"  ferramenta errada  : {errado}/{total}")
    if amostras:
        print("\nreciclagens:")
        for p, t in amostras[:4]:
            print(f"  {p}\n     {t}")


if __name__ == "__main__":
    main()
