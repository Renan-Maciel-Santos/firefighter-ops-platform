# ==========================================
# EXPORTA AFASTAMENTOS DE 2025 PARA EXCEL
# ==========================================
# Critério: qualquer afastamento que "tocou" o ano de 2025
#   - começou em 2025, OU
#   - começou antes e terminou em 2025+, OU
#   - ainda está em aberto (data_fim NULL) e começou até 31/12/2025
# ==========================================

import pandas as pd
import psycopg2
from datetime import datetime

# Acima: Credenciais vêm do .env da raiz — nunca do fonte, que é versionado.
# Acima: Sem valor padrão para a senha, de propósito: um padrão é um segredo no código.
import os as _os, sys as _sys
_sys.path.append(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from _env import exigir, opcional

PG_HOST = opcional("PG_HOST", "localhost")
PG_PORT = int(opcional("PG_PORT", "5432"))
PG_DB   = opcional("PG_DB", "11gb")
PG_USER = opcional("PG_USER", "admin")
PG_PASS = exigir("PG_PASS")

ANO_INICIO = "2026-01-01"
ANO_FIM    = "2026-05-31"

ARQUIVO_SAIDA = f"afastamentos_2025_{datetime.now():%Y%m%d_%H%M%S}.xlsx"


# ==========================================
# CONEXÃO
# ==========================================

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASS,
    options="-c client_encoding=UTF8",
)


# ==========================================
# QUERY PRINCIPAL (DETALHE)
# ==========================================

sql_detalhe = """
    SELECT
        a.re,
        e.nome,
        e.posto_grad,
        e.lotacao,
        a.opm,
        a.motivo_grupo            AS motivo,
        a.motivo_original,
        a.origem_informacao,
        a.data_inicio,
        a.data_fim,
        a.quantidade_dias,
        a.dt_cadastro,
        a.observacao
    FROM b1.v_afastamentos_dedup a
    LEFT JOIN b1.vw_efetivo_classificado e ON e.re = a.re
    WHERE a.data_inicio <= %(fim)s
      AND (a.data_fim IS NULL OR a.data_fim >= %(ini)s)
    ORDER BY a.data_inicio, a.re;
"""

df_det = pd.read_sql(
    sql_detalhe,
    conn,
    params={"ini": ANO_INICIO, "fim": ANO_FIM},
)

print(f"📋 Detalhe: {len(df_det)} linhas")


# ==========================================
# RESUMO POR MOTIVO
# ==========================================

sql_motivo = """
    SELECT
        a.motivo_grupo AS motivo,
        count(*)                       AS afastamentos,
        count(DISTINCT a.re)           AS militares,
        sum(a.quantidade_dias)         AS soma_dias,
        round(avg(a.quantidade_dias)::numeric, 1) AS media_dias
    FROM b1.v_afastamentos_dedup a
    WHERE a.data_inicio <= %(fim)s
      AND (a.data_fim IS NULL OR a.data_fim >= %(ini)s)
    GROUP BY 1
    ORDER BY militares DESC, afastamentos DESC;
"""

df_motivo = pd.read_sql(
    sql_motivo,
    conn,
    params={"ini": ANO_INICIO, "fim": ANO_FIM},
)


# ==========================================
# RESUMO POR MILITAR (TOP)
# ==========================================

sql_militar = """
    SELECT
        a.re,
        e.nome,
        e.posto_grad,
        e.lotacao,
        count(*)                AS qtd_afastamentos,
        sum(a.quantidade_dias)  AS total_dias,
        count(DISTINCT a.motivo_grupo) AS motivos_distintos
    FROM b1.v_afastamentos_dedup a
    LEFT JOIN b1.vw_efetivo_classificado e ON e.re = a.re
    WHERE a.data_inicio <= %(fim)s
      AND (a.data_fim IS NULL OR a.data_fim >= %(ini)s)
    GROUP BY 1, 2, 3, 4
    ORDER BY total_dias DESC NULLS LAST, qtd_afastamentos DESC;
"""

df_militar = pd.read_sql(
    sql_militar,
    conn,
    params={"ini": ANO_INICIO, "fim": ANO_FIM},
)


# ==========================================
# RESUMO POR MÊS
# ==========================================

sql_mes = """
    SELECT
        to_char(a.data_inicio, 'YYYY-MM') AS mes,
        count(*)                           AS afastamentos,
        count(DISTINCT a.re)               AS militares,
        sum(a.quantidade_dias)             AS soma_dias
    FROM b1.v_afastamentos_dedup a
    WHERE a.data_inicio BETWEEN %(ini)s AND %(fim)s
    GROUP BY 1
    ORDER BY 1;
"""

df_mes = pd.read_sql(
    sql_mes,
    conn,
    params={"ini": ANO_INICIO, "fim": ANO_FIM},
)


conn.close()


# ==========================================
# ESCREVE EXCEL (MULTI-ABAS)
# ==========================================

with pd.ExcelWriter(ARQUIVO_SAIDA, engine="openpyxl") as writer:
    df_det.to_excel(writer, sheet_name="Detalhe", index=False)
    df_motivo.to_excel(writer, sheet_name="Por Motivo", index=False)
    df_mes.to_excel(writer, sheet_name="Por Mes", index=False)
    df_militar.to_excel(writer, sheet_name="Por Militar", index=False)

print(f"\n✅ Excel gerado: {ARQUIVO_SAIDA}")
print(f"   - Aba 'Detalhe':    {len(df_det)} linhas")
print(f"   - Aba 'Por Motivo': {len(df_motivo)} linhas")
print(f"   - Aba 'Por Mes':    {len(df_mes)} linhas")
print(f"   - Aba 'Por Militar':{len(df_militar)} linhas")
