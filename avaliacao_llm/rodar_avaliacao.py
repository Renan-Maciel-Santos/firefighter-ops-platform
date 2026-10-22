"""
Mede se um modelo escolhe a ferramenta certa — e quanto tempo leva pra isso.

Roda as perguntas de perguntas.json contra um endpoint compatível com a API da
OpenAI (serve tanto pra api.openai.com quanto pro Ollama em :11434/v1),
usando o system prompt e as 20 tools reais extraídas do workflow.

Três métricas:
    - acerto de roteamento: escolheu a tool esperada?
    - latência: separando prefill (tempo até o 1º token) do total.
      Numa CPU sem GPU o prefill dos ~4k tokens de prompt+schemas costuma ser o
      gargalo, não a geração — por isso as duas medidas vêm separadas.
    - custo: tokens consumidos e o preço disso em dólar, pela tabela de
      precos_llm.py. Sem isso a comparação entre modelos responde "qual acerta
      mais" mas não "quanto custa acertar" — e é a segunda pergunta que decide
      se vale trocar de modelo.

Uso:
    # local (Ollama)
    python rodar_avaliacao.py --modelo qwen3:4b-instruct
    python rodar_avaliacao.py --modelo qwen2.5:7b-instruct

    # nuvem, pra ter a linha de base
    python rodar_avaliacao.py --modelo gpt-4o-mini --base-url https://api.openai.com/v1 --api-key sk-...

Gera: resultado_<modelo>.json  e um resumo no terminal.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

AQUI = Path(__file__).parent

# Acima: tabela de preços na raiz (precos_llm.py), fora da lógica da bancada.
import sys as _sys
_sys.path.append(str(AQUI.parent))
from precos_llm import COTACAO_PADRAO, custo_usd, formatar  # noqa: E402


def carregar(arquivo_prompt="system_prompt.txt"):
    sp = (AQUI / arquivo_prompt).read_text(encoding="utf-8")
    tools = json.loads((AQUI / "tools_openai.json").read_text(encoding="utf-8"))
    perguntas = json.loads((AQUI / "perguntas.json").read_text(encoding="utf-8"))
    return sp, tools, perguntas


def montar_mensagens(system_prompt, pergunta):
    """Histórico curto simulando remetente JÁ identificado.

    Sem isso, o system prompt manda chamar identificar_remetente na primeira
    mensagem e TODA pergunta cairia nessa tool — o teste mediria outra coisa.
    """
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "[Meu telefone: +5512900000000] Bom dia"},
        {"role": "assistant", "content": "Bom dia, Comandante. Às ordens."},
        {"role": "user", "content": f"[Meu telefone: +5512900000000] {pergunta}"},
    ]


# Acima: Famílias de raciocínio (o1..o9, gpt-5). Elas REJEITAM temperature diferente de 1
# com HTTP 400 "unsupported_value" — mandar 0.2 faria as 40 perguntas falharem de uma vez.
MODELOS_DE_RACIOCINIO = re.compile(r"^(o[1-9]|gpt-5)", re.I)


def aceita_temperature(modelo):
    return not MODELOS_DE_RACIOCINIO.match(modelo)


def ler_uso(corpo_resposta):
    """Tokens da resposta, no formato da API da OpenAI.

    Separa dois números que a soma esconde:
      - raciocinio: cobrado como SAÍDA. Nos modelos gpt-5 ele é a maior parte
        da conta, e some se olhar só completion_tokens agregado.
      - cacheados: cobrados a ~10%. É o que faz a fatura real ficar abaixo da
        estimativa de quem multiplica prompt_tokens pelo preço cheio.
    """
    u = (corpo_resposta or {}).get("usage") or {}
    if not u:
        return None
    return {
        "entrada": u.get("prompt_tokens", 0),
        "saida": u.get("completion_tokens", 0),
        "raciocinio": (u.get("completion_tokens_details") or {})
                      .get("reasoning_tokens", 0),
        "cacheados": (u.get("prompt_tokens_details") or {})
                     .get("cached_tokens", 0),
    }


def uma_chamada(base_url, api_key, modelo, mensagens, tools, timeout,
                temperatura=0.2, esforco=None):
    """Retorna (tool_escolhida, args, latencia_total, erro, uso)."""
    corpo = {
        "model": modelo,
        "messages": mensagens,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
    }

    # Acima: Só manda temperature para quem aceita. Medir o modelo de produção exige
    # falar com ele nos termos dele.
    if aceita_temperature(modelo):
        corpo["temperature"] = temperatura

    # Acima: O esforço de raciocínio muda latência e qualidade o bastante para que medir
    # sem ele seja medir outra configuração. Produção roda em 'low'.
    if esforco:
        corpo["reasoning_effort"] = esforco
    t0 = time.perf_counter()
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json=corpo,
            timeout=timeout,
        )
    except Exception as e:
        return None, None, time.perf_counter() - t0, f"exceção: {e}", None

    dt = time.perf_counter() - t0
    if not r.ok:
        return None, None, dt, f"HTTP {r.status_code}: {r.text[:200]}", None

    try:
        corpo_resposta = r.json()
        msg = corpo_resposta["choices"][0]["message"]
    except Exception as e:
        return None, None, dt, f"resposta inesperada: {e}", None

    # Acima: o uso vale mesmo quando o modelo erra a tool — resposta errada
    # também é cobrada, e é justamente ela que encarece um modelo ruim.
    uso = ler_uso(corpo_resposta)

    chamadas = msg.get("tool_calls") or []
    if not chamadas:
        return None, None, dt, None, uso  # respondeu em texto, sem tool

    fn = chamadas[0]["function"]
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except Exception:
        args = {"_bruto": fn.get("arguments")}
    return fn["name"], args, dt, None, uso


def normalizar(v):
    """Compara parâmetros ignorando acento, caixa, ordinal e pontuação."""
    if v is None:
        return ""
    v = str(v).lower().strip()
    for a, b in [("á", "a"), ("â", "a"), ("ã", "a"), ("é", "e"), ("ê", "e"),
                 ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"), ("ú", "u"),
                 ("ç", "c"), ("º", ""), ("°", ""), ("ª", "")]:
        v = v.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--api-key", default="ollama")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--prompt", default="system_prompt.txt",
                    help="arquivo do system prompt (pra comparar original vs corrigido)")
    ap.add_argument("--sufixo", default="",
                    help="sufixo do arquivo de resultado, pra não sobrescrever")
    ap.add_argument("--temperature", type=float, default=0.2,
                    help="ignorado em modelos de raciocínio (o1+, gpt-5), que só aceitam o padrão")
    ap.add_argument("--reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"],
                    help="só para modelos de raciocínio; produção da B.I.A. usa 'low'")
    args = ap.parse_args()

    # Acima: Sem --api-key, cai na variável de ambiente. Evita a chave no histórico do
    # shell e na lista de processos, onde qualquer um da máquina a lê.
    if args.api_key == "ollama" and os.environ.get("OPENAI_API_KEY") \
            and "openai.com" in args.base_url:
        args.api_key = os.environ["OPENAI_API_KEY"]

    system_prompt, tools, perguntas = carregar(args.prompt)
    print(f"modelo: {args.modelo}  |  endpoint: {args.base_url}")
    print(f"{len(perguntas)} perguntas, {len(tools)} tools, "
          f"system prompt de {len(system_prompt)} caracteres\n")

    resultados, acertos, latencias = [], 0, []
    usos = []

    for p in perguntas:
        msgs = montar_mensagens(system_prompt, p["pergunta"])
        tool, got_args, dt, erro, uso = uma_chamada(
            args.base_url, args.api_key, args.modelo, msgs, tools, args.timeout,
            temperatura=args.temperature, esforco=args.reasoning_effort,
        )
        latencias.append(dt)
        if uso:
            usos.append(uso)

        ok_tool = (tool == p["tool"])

        # parâmetros só contam quando a tool já está certa
        ok_params, detalhe_params = True, ""
        if ok_tool and p.get("params"):
            for k, esperado in p["params"].items():
                obtido = (got_args or {}).get(k)
                if normalizar(obtido) != normalizar(esperado):
                    ok_params = False
                    detalhe_params += f" [{k}: esperado {esperado!r}, veio {obtido!r}]"

        ok = ok_tool and ok_params
        acertos += 1 if ok else 0

        marca = "OK  " if ok else "ERRO"
        esperado_txt = p["tool"] or "(nenhuma)"
        obtido_txt = tool or "(nenhuma)"
        linha = f"{marca} #{p['id']:02d} [{dt:6.1f}s] {p['pergunta'][:46]:46s}"
        if not ok:
            linha += f" -> esperado {esperado_txt}, veio {obtido_txt}{detalhe_params}"
        if erro:
            linha += f"  !! {erro}"
        print(linha)

        resultados.append({**p, "obtido": tool, "args": got_args,
                           "ok": ok, "latencia_s": round(dt, 2), "erro": erro,
                           "uso": uso})

    n = len(perguntas)
    lat_ord = sorted(latencias)
    resumo = {
        "modelo": args.modelo,
        "endpoint": args.base_url,
        # Acima: Sem registrar a configuração, dois resultados do mesmo modelo viram
        # números incomparáveis daqui a um mês — ninguém lembra com que esforço rodou.
        "reasoning_effort": args.reasoning_effort,
        "temperature": args.temperature if aceita_temperature(args.modelo) else None,
        "prompt": args.prompt,
        "total": n,
        "acertos": acertos,
        "taxa_acerto_pct": round(100 * acertos / n, 1),
        "latencia_media_s": round(sum(latencias) / n, 2),
        "latencia_mediana_s": round(lat_ord[n // 2], 2),
        "latencia_max_s": round(max(latencias), 2),
    }

    # Acima: uma pergunta da bancada é UMA chamada; a B.I.A. em produção gasta
    # ~1,8 por mensagem (escolher a tool + redigir a resposta com o resultado).
    # O custo por mensagem real é ~2x o daqui — comparar modelos entre si, que
    # é a função deste script, continua valendo.
    if usos:
        ent = sum(u["entrada"] for u in usos) / len(usos)
        sai = sum(u["saida"] for u in usos) / len(usos)
        rac = sum(u["raciocinio"] for u in usos) / len(usos)
        cac = sum(u["cacheados"] for u in usos) / len(usos)
        c_teto = custo_usd(args.modelo, ent, sai)
        c_real = custo_usd(args.modelo, ent, sai, entrada_cacheada=cac)
        resumo.update({
            "tokens_entrada_medio": round(ent),
            "tokens_saida_medio": round(sai),
            "tokens_raciocinio_medio": round(rac),
            "tokens_cacheados_medio": round(cac),
            "custo_usd_por_chamada": round(c_real, 8) if c_real is not None else None,
            "custo_usd_bancada": round(c_real * len(usos), 6) if c_real is not None else None,
            "respostas_com_uso": len(usos),
        })

    print(f"\n{'='*60}")
    print(f"acerto de roteamento: {acertos}/{n}  ({resumo['taxa_acerto_pct']}%)")
    print(f"latência  média {resumo['latencia_media_s']}s"
          f" | mediana {resumo['latencia_mediana_s']}s"
          f" | pior {resumo['latencia_max_s']}s")

    if usos:
        # Acima: milhar com ponto, como o resto do relatório. Os valores são
        # inteiros, então trocar a vírgula direto é seguro aqui.
        mil = lambda v: f"{v:,.0f}".replace(",", ".")
        print(f"tokens    entrada {mil(ent)} | saída {mil(sai)}"
              f" (raciocínio {mil(rac)}) | cacheados {mil(cac)}")
        print(f"custo     {formatar(c_real)} por chamada"
              + (f"  [teto sem cache: {formatar(c_teto)}]"
                 if c_teto and c_real != c_teto else ""))
        if resumo.get("custo_usd_bancada"):
            print(f"          esta bancada de {len(usos)} perguntas custou "
                  f"{formatar(c_real * len(usos))}")
        if len(usos) < n:
            print(f"[!] {n - len(usos)} chamadas não retornaram usage "
                  f"(endpoint não informou) — média sobre as demais")
    else:
        print("tokens    endpoint não devolveu 'usage' — custo não medido")

    nome = args.modelo.replace(":", "_").replace("/", "_") + args.sufixo
    saida = AQUI / f"resultado_{nome}.json"
    saida.write_text(json.dumps({"resumo": resumo, "detalhe": resultados},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"detalhe salvo em {saida.name}")


if __name__ == "__main__":
    main()
