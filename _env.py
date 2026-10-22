# ==========================================================================
# CARREGAMENTO DE CONFIGURAÇÃO E SEGREDOS
# ==========================================================================
# Todo segredo do projeto vem do .env da raiz. Nenhum vai para o fonte, porque
# o repositório é versionado e um valor commitado permanece recuperável no
# histórico mesmo depois de trocado no código.
#
# Uso:
#     from _env import exigir, opcional
#     PG_PASS = exigir("PG_PASS")
#     PG_HOST = opcional("PG_HOST", "localhost")
#
# Funciona de qualquer subpasta (B1/, B4/, webapp/...): o .env é sempre
# procurado na raiz do projeto, junto deste arquivo.
# ==========================================================================

import os
import sys

from dotenv import load_dotenv

# Acima: Raiz do projeto = pasta onde este arquivo mora
RAIZ = os.path.dirname(os.path.abspath(__file__))
CAMINHO_ENV = os.path.join(RAIZ, ".env")

load_dotenv(CAMINHO_ENV)


def exigir(nome, dica=None):
    """Lê uma variável obrigatória. Falha cedo e explicando, em vez de tarde e confuso."""
    valor = os.environ.get(nome)
    if valor is None or not valor.strip():
        # Acima: Sem isto o sintoma vira "senha incorreta" ou "token inválido" —
        # erro que manda procurar no lugar errado. Aqui o problema é dito por extenso.
        msg = (
            f"\n❌ Variável obrigatória ausente: {nome}\n"
            f"   Defina em {CAMINHO_ENV}\n"
        )
        if dica:
            msg += f"   {dica}\n"
        print(msg, file=sys.stderr)
        raise SystemExit(1)
    return valor.strip()


def opcional(nome, padrao=None):
    """Lê uma variável que tem padrão sensato. Nunca use para segredo."""
    valor = os.environ.get(nome)
    return valor.strip() if valor and valor.strip() else padrao
