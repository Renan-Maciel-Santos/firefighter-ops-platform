"""
Coleta de dados operacionais da COBOM/CBI — vítimas fatais e ocorrências.

Arquivo fonte esperado em:
    dados_externos\\cobom_<ANO>-S<SEM>.xlsx

Layout do xlsx (fixo, 4 blocos empilhados verticalmente):
    linha 1:  título "Quantidade de vítimas fatais em ocorrências de incêndio"
    linha 2:  cabeçalho de meses (Jan..Jun para S1, Jul..Dez para S2)
    linhas 3-6: 1º Sgb .. 4º Sgb
    linha 7:  título próximo bloco (ocorrências de incêndio)
    linhas 8-12: cabeçalho + 4 SGBs
    ... (repete para acidente de trânsito: fatais + ocorrências)

Não há dado da Sede — ocorrências são despachadas por área geográfica.
"""

import os, openpyxl
from calendar import month_abbr

DIR_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados_externos")

# Rótulos que aparecem no xlsx (case + acentos exatos, sem depender de encoding do print)
BLOCOS = [
    ("fatais_incendio",   "vítimas fatais em ocorrências de incêndio"),
    ("ocorrencias_incendio", "ocorrências de incêndio"),
    ("fatais_transito",   "vítimas fatais em ocorrências de acidente de trânsito"),
    ("ocorrencias_transito", "ocorrências de acidente de trânsito"),
]

# Meses (chave curta pt-br) → índice 1..12
MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def _semestre_de_mes(m):
    return 1 if m <= 6 else 2


def _norm_sgb(s):
    if not s: return None
    s = str(s).upper().replace("°", "º").strip()
    import re
    m = re.match(r"(\d)\s*º?\s*S?GB", s)
    return f"{m.group(1)}_SGB" if m else None


def _ler_arquivo(caminho):
    """Retorna dict {bloco: {'1_SGB': {1: v, 2: v, ...}, ...}}"""
    wb = openpyxl.load_workbook(caminho, data_only=True)
    ws = wb.active
    linhas = list(ws.iter_rows(values_only=True))

    resultado = {chave: {} for chave, _ in BLOCOS}
    idx = 0
    while idx < len(linhas):
        linha = linhas[idx]
        titulo = (linha[0] or "").strip() if linha else ""
        titulo_norm = titulo.lower().replace("\n", " ").replace("  ", " ")

        bloco_chave = None
        for chave, rotulo in BLOCOS:
            if rotulo in titulo_norm:
                bloco_chave = chave; break

        if not bloco_chave:
            idx += 1; continue

        # próxima linha = cabeçalho de meses; 4 linhas seguintes = SGBs
        cabecalho = linhas[idx + 1]
        meses_cols = []
        for j in range(1, len(cabecalho)):
            nome = str(cabecalho[j] or "").strip().lower()[:3]
            meses_cols.append(MESES.get(nome))

        for row_offset in range(2, 6):
            if idx + row_offset >= len(linhas): break
            linha_sgb = linhas[idx + row_offset]
            sgb = _norm_sgb(linha_sgb[0])
            if not sgb: continue
            valores_por_mes = {}
            for j, mes in enumerate(meses_cols, start=1):
                if mes and linha_sgb[j] is not None:
                    valores_por_mes[mes] = int(linha_sgb[j])
            resultado[bloco_chave][sgb] = valores_por_mes

        idx += 6

    return resultado


def _somar_meses(mapa_mes_valor, meses_alvo):
    return sum(mapa_mes_valor.get(m, 0) for m in meses_alvo)


def coletar(ano, meses_alvo):
    """
    Coleta agregada da COBOM para uma lista de meses (1..12) em um dado ano.
    Pode cruzar semestres — abre 1 ou 2 arquivos conforme necessário.
    Retorna dict com 4 blocos × por_sgb + geral.
    """
    sems_necessarios = sorted({_semestre_de_mes(m) for m in meses_alvo})
    dados_brutos = {chave: {} for chave, _ in BLOCOS}

    for sem in sems_necessarios:
        caminho = os.path.join(DIR_DADOS, f"cobom_{ano}-S{sem}.xlsx")
        if not os.path.exists(caminho):
            continue
        parcial = _ler_arquivo(caminho)
        for chave in dados_brutos:
            for sgb, mapa in parcial[chave].items():
                dados_brutos[chave].setdefault(sgb, {}).update(mapa)

    sgbs = ["1_SGB", "2_SGB", "3_SGB", "4_SGB"]
    resultado = {}
    for chave, _ in BLOCOS:
        por_sgb = []
        total = 0
        for sgb in sgbs:
            v = _somar_meses(dados_brutos[chave].get(sgb, {}), meses_alvo)
            por_sgb.append({"sgb": sgb, "valor": v})
            total += v
        resultado[chave] = {"total": total, "por_sgb": por_sgb}

    # Taxa letalidade (mortos por 100 ocorrências) — útil no relatório
    def _pct(num, den):
        return round(100 * num / den, 2) if den else 0
    resultado["letalidade_incendio_pct"] = _pct(
        resultado["fatais_incendio"]["total"],
        resultado["ocorrencias_incendio"]["total"])
    resultado["letalidade_transito_pct"] = _pct(
        resultado["fatais_transito"]["total"],
        resultado["ocorrencias_transito"]["total"])

    return resultado


if __name__ == "__main__":
    import json
    # Teste rápido: S1/2026 completo
    r = coletar(2026, list(range(1, 7)))
    print(json.dumps(r, indent=2, ensure_ascii=False))
