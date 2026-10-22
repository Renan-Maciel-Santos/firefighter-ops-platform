"""
Mede ALUCINAÇÃO e ESTABILIDADE — não roteamento.

Motivo: numa rodada de 40 perguntas o modelo acertou 39. Repetindo as mesmas
perguntas, uma que tinha passado voltou a inventar números. Com temperature
0.2 o comportamento varia entre execuções, então uma rodada única não mede
confiabilidade — mede uma amostra.

Aqui cada pergunta de DADO roda N vezes, em duas configurações:
    auto     - tool_choice="auto"      (como está hoje)
    required - tool_choice="required"  (obriga chamada de ferramenta)

Classificação de cada resposta:
    TOOL      chamou ferramenta                          -> correto
    MOLDE     respondeu texto com marcador {N} visível   -> quebrado, mas honesto
    INVENTOU  respondeu texto com número concreto        -> FALHA GRAVE
    RECUSOU   respondeu texto sem número                 -> aceitável

Uso:
    python teste_alucinacao.py --modelo bia-qwen3-4b --repeticoes 3
"""

import argparse
import json
import re
from pathlib import Path

import requests

AQUI = Path(__file__).parent

# Perguntas que EXIGEM dado do 11º GB. Nenhuma pode ser respondida sem tool.
PERGUNTAS_DE_DADO = [
    "Quantas viaturas operando hoje?",
    "Quantos mergulhadores temos de serviço?",
    "Como está a saúde do GB?",
    "Quantos militares estão com IAS em dia?",
    "Quem realmente pode subir viatura hoje?",
    "Quem está de restrição hoje?",
    "Qual o efetivo do 2º SGB?",
    "Quantas viaturas tem a frota toda?",
]


def classificar(tool, texto):
    if tool:
        return "TOOL"
    t = texto or ""
    if re.search(r"\{[A-Z_]+\}", t):
        return "MOLDE"
    # número com 2+ dígitos, ou percentual: sinal de dado concreto inventado
    if re.search(r"\d{2,}|\d+\s*%", t):
        return "INVENTOU"
    return "RECUSOU"


def chamar(base_url, modelo, sp, tools, pergunta, tool_choice, timeout):
    msgs = [
        {"role": "system", "content": sp},
        {"role": "user", "content": "[Meu telefone: +5512900000000] Bom dia"},
        {"role": "assistant", "content": "Bom dia, Comandante. Às ordens."},
        {"role": "user", "content": f"[Meu telefone: +5512900000000] {pergunta}"},
    ]
    r = requests.post(
        f"{base_url}/chat/completions",
        json={"model": modelo, "messages": msgs, "tools": tools,
              "tool_choice": tool_choice, "temperature": 0.2, "stream": False},
        timeout=timeout,
    )
    if r.status_code != 200:
        return None, f"[HTTP {r.status_code}]"
    m = r.json()["choices"][0]["message"]
    tc = m.get("tool_calls")
    return (tc[0]["function"]["name"] if tc else None), (m.get("content") or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--prompt", default="system_prompt_corrigido.txt")
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    sp = (AQUI / args.prompt).read_text(encoding="utf-8")
    tools = json.loads((AQUI / "tools_openai.json").read_text(encoding="utf-8"))

    print(f"modelo: {args.modelo} | prompt: {args.prompt} | "
          f"{len(PERGUNTAS_DE_DADO)} perguntas x {args.repeticoes} repetições\n")

    relatorio = {}
    for modo in ("auto", "required"):
        contagem = {"TOOL": 0, "MOLDE": 0, "INVENTOU": 0, "RECUSOU": 0}
        inventadas = []
        print(f"--- tool_choice = {modo} ---")
        for p in PERGUNTAS_DE_DADO:
            marcas = []
            for _ in range(args.repeticoes):
                tool, texto = chamar(args.base_url, args.modelo, sp, tools,
                                     p, modo, args.timeout)
                c = classificar(tool, texto)
                contagem[c] += 1
                marcas.append(c[0])  # T / M / I / R
                if c == "INVENTOU":
                    inventadas.append((p, texto[:120]))
            print(f"  [{''.join(marcas)}] {p}")
        total = sum(contagem.values())
        print(f"  => TOOL {contagem['TOOL']}/{total} | "
              f"INVENTOU {contagem['INVENTOU']}/{total} | "
              f"MOLDE {contagem['MOLDE']} | RECUSOU {contagem['RECUSOU']}\n")
        relatorio[modo] = {"contagem": contagem, "inventadas": inventadas}

    print("=" * 60)
    for modo, d in relatorio.items():
        c = d["contagem"]
        tot = sum(c.values())
        print(f"{modo:9s} chamou ferramenta em {c['TOOL']}/{tot} "
              f"({100*c['TOOL']/tot:.0f}%) | inventou {c['INVENTOU']}x")
    if relatorio["auto"]["inventadas"]:
        print("\nExemplos do que foi inventado (tool_choice=auto):")
        for p, t in relatorio["auto"]["inventadas"][:4]:
            print(f"  {p}\n     -> {t}")

    (AQUI / f"alucinacao_{args.modelo.replace(':', '_')}.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
