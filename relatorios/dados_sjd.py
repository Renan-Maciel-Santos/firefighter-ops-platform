"""
Leitura de dados do SJD para o relatório PPTX — agora consumindo do Postgres.

O ETL `SJD/sjd_etl.py` carrega o xlsx nas tabelas sjd.processos e
sjd.indicadores_mensais. Este módulo lê apenas do banco (fonte única de verdade).

Chave pública: coletar(ano, meses_alvo) → dict de KPIs consolidados no período.
"""

import os, sys
from datetime import date
from calendar import monthrange

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _comum import conectar_postgres


PUNICOES_EFETIVAS = {
    "REPREENSÃO", "REPREENSAO",
    "PERMANÊNCIA", "PERMANENCIA",       # sanção disciplinar RDPM Art. 14
    "DETENÇÃO", "DETENCAO",
    "PRISÃO", "PRISAO",
    "IMPEDIMENTO",
    "LICENCIAMENTO A BEM DA DISCIPLINA",
    "EXCLUSÃO", "EXCLUSAO",
    "DEMISSÃO", "DEMISSAO",
    "REFORMA COMPULSÓRIA", "REFORMA COMPULSORIA",
}


def _norm_upper(s):
    if s is None: return ""
    return str(s).strip().upper() \
        .replace("Ç", "C").replace("Ã", "A").replace("Õ", "O") \
        .replace("Á", "A").replace("É", "E").replace("Í", "I") \
        .replace("Ó", "O").replace("Ú", "U")


def coletar(ano, meses_alvo):
    """Retorna dict com KPIs consolidados no intervalo [min(meses)..max(meses)] do ano."""
    if not meses_alvo:
        return None
    inicio = date(ano, min(meses_alvo), 1)
    fim = date(ano, max(meses_alvo), monthrange(ano, max(meses_alvo))[1])

    conn = conectar_postgres()
    cur = conn.cursor()
    try:
        # Indicadores mensais agregados (Plan2)
        cur.execute("""
            SELECT indicador, SUM(valor) AS total
            FROM sjd.indicadores_mensais
            WHERE ano = %s AND mes = ANY(%s)
            GROUP BY indicador
        """, (ano, list(meses_alvo)))
        agregados = {r[0]: int(r[1]) for r in cur.fetchall()}

        # PDs com decisão de pena efetiva no período (conta cada evento — 1 militar
        # que foi punido 2x em datas distintas soma como 2)
        cur.execute("""
            SELECT punicao FROM sjd.processos
            WHERE tipo = 'PD'
              AND data_abertura BETWEEN %s AND %s
              AND punicao IS NOT NULL
        """, (inicio, fim))
        punidos = sum(1 for r in cur.fetchall() if _norm_upper(r[0]) in PUNICOES_EFETIVAS)

        # Total de processos abertos no período (métrica auxiliar)
        cur.execute("""
            SELECT COUNT(*) FROM sjd.processos
            WHERE data_abertura BETWEEN %s AND %s
        """, (inicio, fim))
        total_periodo = cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

    return {
        "acidentes_folga_bombeiro": agregados.get("acidentes_folga_bombeiro", 0),
        "acidentes_viatura_vitima": agregados.get("acidentes_viatura_vitima", 0),
        "reclamacoes_denuncias":    agregados.get("reclamacoes_denuncias", 0),
        "pms_punidos_pd":           punidos,
        "total_processos_periodo":  total_periodo,
    }


if __name__ == "__main__":
    r = coletar(2026, list(range(1, 7)))
    for k, v in r.items():
        print(f"  {k:30s} {v}")
