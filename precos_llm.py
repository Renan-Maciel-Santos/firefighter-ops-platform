# ==========================================================================
# TABELA DE PREÇOS DOS MODELOS DE LINGUAGEM
# ==========================================================================
# Um lugar só para o preço dos modelos de nuvem usados como linha de base na
# bancada de avaliação (avaliacao_llm/rodar_avaliacao.py), separado do código
# para ser conferido e atualizado sem mexer na lógica.
#
# Valores em DÓLAR POR MILHÃO DE TOKENS.
#
# ⚠ CONFERIR em https://openai.com/api/pricing antes de usar o número em
#   qualquer coisa que vire decisão ou relatório. Preço de API muda sem aviso
#   e esta tabela é uma cópia — a fonte da verdade é a fatura.
#   Última conferência manual: NUNCA (preencha a data ao validar).
#
# Uso:
#     from precos_llm import custo_usd
#     custo_usd("gpt-5-mini", entrada=6282, saida=132)
# ==========================================================================

# Acima: entrada / entrada_cacheada / saída. O preço cacheado existe porque a
# OpenAI cobra ~10% no trecho repetido de prompts acima de 1024 tokens — e o
# system prompt da B.I.A. tem ~4k tokens fixos em toda chamada, então esse
# desconto é a maior parte da diferença entre a conta estimada e a fatura.
PRECOS = {
    "gpt-5":      {"entrada": 1.25, "cacheada": 0.125, "saida": 10.00},
    "gpt-5-mini": {"entrada": 0.25, "cacheada": 0.025, "saida":  2.00},
    "gpt-5-nano": {"entrada": 0.05, "cacheada": 0.005, "saida":  0.40},
    "gpt-4o-mini":{"entrada": 0.15, "cacheada": 0.075, "saida":  0.60},
    "gpt-4o":     {"entrada": 2.50, "cacheada": 1.25,  "saida": 10.00},
}

# Acima: Modelo rodando no Ollama da própria máquina não tem preço por token.
# O custo dele é energia e hardware, que não se mede por mensagem.
GRATUITOS = ("bia-", "qwen", "llama", "mistral", "gemma", "deepseek")

COTACAO_PADRAO = 5.40   # BRL por USD — ajuste na chamada quando importar precisão


def tabela(modelo):
    """Preço do modelo, casando por prefixo (gpt-5-mini-2026-01-01 → gpt-5-mini)."""
    if not modelo:
        return None
    m = modelo.lower().strip()

    if m.startswith(GRATUITOS):
        return {"entrada": 0.0, "cacheada": 0.0, "saida": 0.0}

    # Acima: Do mais específico para o mais genérico. Sem ordenar por tamanho,
    # "gpt-5" casaria antes de "gpt-5-mini" e o custo sairia 5x maior.
    for nome in sorted(PRECOS, key=len, reverse=True):
        if m.startswith(nome):
            return PRECOS[nome]
    return None


def custo_usd(modelo, entrada, saida, entrada_cacheada=0):
    """Custo em dólares. Devolve None quando o modelo não está na tabela.

    entrada_cacheada é o pedaço de `entrada` que veio do cache — cobrado à
    parte. Passe 0 para ter o teto do custo.
    """
    p = tabela(modelo)
    if p is None:
        return None
    nova = max(entrada - entrada_cacheada, 0)
    return (nova * p["entrada"]
            + entrada_cacheada * p["cacheada"]
            + saida * p["saida"]) / 1_000_000


def formatar(usd, cotacao=COTACAO_PADRAO):
    """US$ 0,003100 (R$ 0,0167) — casas suficientes para custo por mensagem."""
    if usd is None:
        return "modelo fora da tabela"
    return f"US$ {usd:.6f} (R$ {usd * cotacao:.4f})".replace(".", ",")
