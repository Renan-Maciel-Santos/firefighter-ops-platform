"""
Testa CONVERSA, não pergunta isolada.

Buraco descoberto em produção (execução 1584, 11/08/2026): depois de consultar
um militar, o Comandante perguntou 'como está a IAS e TAF dele?'. O modelo NÃO
chamou ferramenta — montou a resposta a partir do resultado que já estava na
memória da conversa, e montou errado:

    Elogios: 2024 — 2025
    TAF: 2024 — 2025
    IAS: Atualizado há 3 dias — 2024 — 2025 (sem restrições)

Os outros arnesses testam pergunta isolada, com histórico fixo de 3 mensagens.
Nunca exercitaram: (a) memória com resultados de ferramenta acumulados,
(b) pergunta com pronome referencial ('dele', 'e o TAF?').

Este script simula a conversa com o retorno de ferramenta JÁ no histórico —
que é justamente a condição que induz o modelo a reciclar em vez de consultar.

Uso:
    python teste_multiturno.py --modelo bia-qwen3-4b --prompt system_prompt_v9.txt
"""

import argparse
import json
from pathlib import Path

import requests

AQUI = Path(__file__).parent

# Retorno real de /consulta/militar, como o agente o vê.
RETORNO_MILITAR = json.dumps({
    "total": 1,
    "mensagem": "👮 CB PM RAFAEL DUARTE LIMA (RE 900003)\n📍 *ATIVO* — 11º GB",
}, ensure_ascii=False)

# Cada caso: (pergunta de acompanhamento, ferramenta que DEVE ser chamada)
CASOS = [
    ("como está a IAS e TAF dele?", {"consultar_ias", "consultar_taf", "dossie_militar"}),
    ("e a IAS dele?", {"consultar_ias", "dossie_militar"}),
    ("ele tem restrição?", {"consultar_restricoes", "dossie_militar"}),
    ("e o TAF?", {"consultar_taf", "dossie_militar"}),
    ("quantos elogios ele tem?", {"consultar_elogios_militar", "dossie_militar"}),
    ("me dá o panorama completo dele", {"dossie_militar"}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--api-key", default="ollama")
    ap.add_argument("--repeticoes", type=int, default=3)
    args = ap.parse_args()

    sp = (AQUI / args.prompt).read_text(encoding="utf-8")
    tools = json.loads((AQUI / "tools_openai.json").read_text(encoding="utf-8"))

    print(f"modelo: {args.modelo} | prompt: {args.prompt} | "
          f"{len(CASOS)} casos x {args.repeticoes} repetições\n")

    ok = errado = sem_tool = 0
    exemplos = []

    for pergunta, esperadas in CASOS:
        marcas = []
        for _ in range(args.repeticoes):
            msgs = [
                {"role": "system", "content": sp},
                {"role": "user", "content": "[Meu telefone: +5511900000001] bom dia"},
                {"role": "assistant", "content": "Bom dia, Comandante. Às ordens."},
                # turno anterior: consulta já feita, resultado NA MEMÓRIA
                {"role": "user", "content": "[Meu telefone: +5511900000001] me consulte o RE 900003"},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "t1", "type": "function",
                                 "function": {"name": "buscar_militar",
                                              "arguments": '{"re":"900003"}'}}]},
                {"role": "tool", "tool_call_id": "t1", "content": RETORNO_MILITAR},
                {"role": "assistant",
                 "content": "👮 CB PM RAFAEL DUARTE LIMA (RE 900003)\n📍 *ATIVO* — 11º GB"},
                # pergunta de acompanhamento, com pronome
                {"role": "user", "content": f"[Meu telefone: +5511900000001] {pergunta}"},
            ]
            r = requests.post(
                f"{args.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {args.api_key}"},
                json={"model": args.modelo, "messages": msgs, "tools": tools,
                      "temperature": 0.2, "stream": False},
                timeout=900,
            )
            m = r.json()["choices"][0]["message"]
            tc = m.get("tool_calls")
            if tc:
                nome = tc[0]["function"]["name"]
                if nome in esperadas:
                    marcas.append("."); ok += 1
                else:
                    marcas.append("x"); errado += 1
                    exemplos.append((pergunta, f"chamou {nome}"))
            else:
                marcas.append("F"); sem_tool += 1
                exemplos.append((pergunta, "SEM FERRAMENTA: " +
                                 (m.get("content") or "")[:150].replace("\n", " | ")))
        print(f"  [{''.join(marcas)}] {pergunta}")

    total = len(CASOS) * args.repeticoes
    print(f"\n{'='*62}")
    print("legenda: . = consultou certo | x = ferramenta errada | F = NÃO consultou")
    print(f"  consultou corretamente : {ok}/{total}")
    print(f"  ferramenta errada      : {errado}/{total}")
    print(f"  RESPONDEU SEM CONSULTAR: {sem_tool}/{total}   <- fabricação")
    if exemplos:
        print("\nocorrências:")
        for p, d in exemplos[:5]:
            print(f"  {p}\n     {d}")


if __name__ == "__main__":
    main()
