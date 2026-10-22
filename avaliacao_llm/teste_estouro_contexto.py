"""
Testa se a CONVERSA LONGA estoura o contexto e derruba as regras do prompt.

Hipótese (11/08/2026): o prompt fixo (sistema + schemas) ocupa ~4.478 dos
8.192 tokens de contexto. A memória do n8n guarda 10 mensagens, e resultados
de ferramenta são longos (mapa de força, motomec, dossiê). Quando o total
passa de 8.192, o runtime descarta os tokens MAIS ANTIGOS — que são o prompt
de sistema. O modelo perde as regras anti-fabricação e volta a inventar.

Foi o que se viu na execução 1584: depois de 6-7 turnos com consultas, a
resposta a 'como está a IAS e TAF dele?' veio inventada, sem chamar ferramenta.

O teste reconstrói uma conversa crescente e mede, a cada turno, quantos tokens
o prompt ocupa e se o modelo ainda consulta.

Uso:
    python teste_estouro_contexto.py --modelo bia-qwen3-4b --prompt system_prompt_v9.txt
"""

import argparse
import json
from pathlib import Path

import requests

AQUI = Path(__file__).parent

# Retornos REAIS das ferramentas, com o tamanho que eles têm de verdade.
RET = {
    "operacional": "Mapa de Força (atualizado há 8 dias — serviço de 03/08/2026): 36 operando, "
                   "48 reserva, 22 baixada. Efetivo total 95, água 169550L em 31 estações, "
                   "20 mergulhadores. (água e mergulhadores são por estação, não por viatura)",
    "motomec": "Motomec (frota completa): 189 viaturas — 133 operando, 30 baixadas (15.9%), "
               "21 em descarga. Idade média: 10.8 anos.",
    "saude": "❤️ *503 ativos*: 470 EM DIA (93.44%) • 29 ATRASADA (5.77%) • 4 SEM IAS (0.80%) "
             "• 21 com restrição vigente.",
    "efetivo": "Efetivo por lotação (503 ativos): 1°Sgb: 117 • 2°Sgb: 109 • 3°Sgb: 123 "
               "• 4°Sgb: 77 • EM: 77",
    "militar": "👮 CB PM RAFAEL DUARTE LIMA (RE 900003)\n📍 *ATIVO* — 11º GB",
}

# Conversa que cresce, imitando o uso real.
TURNOS = [
    ("bom dia", "identificar_remetente", "Bom dia, Comandante. Às ordens."),
    ("quais as novidades de hoje", "resumo_operacional", RET["operacional"]),
    ("e quantas viaturas nós temos?", "consultar_motomec_resumo", RET["motomec"]),
    ("como está a saúde do GB?", "consultar_saude_geral", RET["saude"]),
    ("e o efetivo por SGB?", "consultar_efetivo_por_lotacao", RET["efetivo"]),
    ("me consulte o RE 900003", "buscar_militar", RET["militar"]),
]

PERGUNTA_FINAL = "como está a IAS e TAF dele?"
ESPERADAS = {"consultar_ias", "consultar_taf", "dossie_militar"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--repeticoes", type=int, default=2)
    args = ap.parse_args()

    sp = (AQUI / args.prompt).read_text(encoding="utf-8")
    tools = json.loads((AQUI / "tools_openai.json").read_text(encoding="utf-8"))

    print(f"modelo: {args.modelo} | prompt: {args.prompt}")
    print("a conversa cresce turno a turno; mede tokens e se ainda consulta\n")

    base = [{"role": "system", "content": sp}]
    hist = []

    for i, (pergunta, tool, resposta) in enumerate(TURNOS, 1):
        hist += [
            {"role": "user", "content": f"[Meu telefone: +5511900000001] {pergunta}"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"t{i}", "type": "function",
                             "function": {"name": tool, "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"t{i}",
             "content": json.dumps({"mensagem": resposta}, ensure_ascii=False)},
            {"role": "assistant", "content": resposta},
        ]

        msgs = base + hist + [
            {"role": "user", "content": f"[Meu telefone: +5511900000001] {PERGUNTA_FINAL}"}
        ]

        marcas, tokens = [], None
        for _ in range(args.repeticoes):
            r = requests.post(f"{args.base_url}/chat/completions",
                              json={"model": args.modelo, "messages": msgs,
                                    "tools": tools, "temperature": 0.2,
                                    "stream": False}, timeout=900)
            if r.status_code != 200:
                marcas.append("E")
                print(f"  turno {i}: HTTP {r.status_code} {r.text[:120]}")
                continue
            d = r.json()
            tokens = d.get("usage", {}).get("prompt_tokens")
            m = d["choices"][0]["message"]
            tc = m.get("tool_calls")
            if tc and tc[0]["function"]["name"] in ESPERADAS:
                marcas.append(".")
            elif tc:
                marcas.append("x")
            else:
                marcas.append("F")
                ultimo = (m.get("content") or "")[:120].replace("\n", " | ")

        aviso = "  <-- ESTOUROU (>8192)" if (tokens or 0) > 8192 else ""
        print(f"  turno {i:2d} ({len(hist)//4} consultas na memória): "
              f"{tokens} tokens  [{''.join(marcas)}]{aviso}")
        if "F" in marcas:
            print(f"        NÃO consultou -> {ultimo}")

    print("\nlegenda: . = consultou | x = ferramenta errada | F = respondeu sem consultar")


if __name__ == "__main__":
    main()
