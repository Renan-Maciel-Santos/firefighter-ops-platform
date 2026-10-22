"""
Exporta qualquer view/tabela do banco 11gb para Excel.
Uso: python exportar_view.py <schema.view> [arquivo_saida.xlsx]
Exemplo: python exportar_view.py b1.vw_afastamentos_out25_abr26
"""

import sys
import psycopg2
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
import os

# ==========================================
# CONFIG
# ==========================================
# Acima: Credenciais vêm do .env da raiz — nunca do fonte, que é versionado.
# Acima: Sem valor padrão para a senha, de propósito: um padrão é um segredo no código.
import os as _os, sys as _sys
_sys.path.append(_os.path.dirname(_os.path.abspath(__file__)))
from _env import exigir, opcional

PG_HOST = opcional("PG_HOST", "localhost")
PG_PORT = int(opcional("PG_PORT", "5432"))
PG_DB   = opcional("PG_DB", "11gb")
PG_USER = opcional("PG_USER", "admin")
PG_PASS = exigir("PG_PASS")

VIEW    = sys.argv[1] if len(sys.argv) > 1 else "b1.vw_afastamentos_out25_abr26"
SAIDA   = sys.argv[2] if len(sys.argv) > 2 else f"{VIEW.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

# ==========================================
# NOMES DE COLUNA AMIGAVEIS
# ==========================================
RENOMEAR = {
    "re":               "RE",
    "nome":             "Nome",
    "posto_grad":       "Posto/Grad",
    "lotacao":          "Lotação",
    "motivo":           "Motivo",
    "data_inicio":      "Início",
    "data_fim":         "Término",
    "quantidade_dias":  "Qtd Dias",
    "opm":              "OPM",
    "origem_informacao":"Origem",
    "observacao":       "Observação",
    "dt_cadastro":      "Dt. Cadastro",
    # elogios
    "nbi":              "NBI",
    "num_bi_11gb":      "BI 11GB",
    "posto_grad":       "Posto/Grad",
    "assunto":          "Assunto",
    "tipo":             "Tipo",
    "data_elogio":      "Data Elogio",
    "data_lancamento":  "Dt. Lançamento",
    "sgb":              "SGB",
    "solenidade":       "Solenidade",
    "mes_ano":          "Mês/Ano",
    "ano":              "Ano",
}

# ==========================================
# BUSCA DADOS
# ==========================================
print(f"[*] Consultando {VIEW} ...")
conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS)
df = pd.read_sql(f"SELECT * FROM {VIEW}", conn)
conn.close()
print(f"[OK] {len(df)} linhas x {len(df.columns)} colunas")

# Renomeia colunas
df.rename(columns={c: RENOMEAR.get(c, c) for c in df.columns}, inplace=True)

# ==========================================
# EXPORTA COM FORMATACAO
# ==========================================
print(f"[*] Gerando {SAIDA} ...")

with pd.ExcelWriter(SAIDA, engine="openpyxl", date_format="DD/MM/YYYY", datetime_format="DD/MM/YYYY") as writer:
    df.to_excel(writer, index=False, sheet_name="Dados")
    ws = writer.sheets["Dados"]

    # Estilo cabeçalho
    HEADER_FILL  = PatternFill("solid", fgColor="1a1a2e")
    HEADER_FONT  = Font(bold=True, color="FFFFFF", size=10)
    HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    BORDER_THIN  = Border(
        bottom=Side(style="thin", color="B22222"),
        right=Side(style="thin",  color="333333"),
    )
    ROW_FILL_PAR = PatternFill("solid", fgColor="F5F5F5")
    ROW_FILL_IMP = PatternFill("solid", fgColor="FFFFFF")
    DATA_FONT    = Font(size=9)
    DATA_ALIGN   = Alignment(vertical="center")

    for col_idx, cell in enumerate(ws[1], start=1):
        cell.fill      = HEADER_FILL
        cell.font      = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border    = BORDER_THIN

    # Linhas de dados com zebra
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
        fill = ROW_FILL_PAR if row_idx % 2 == 0 else ROW_FILL_IMP
        for cell in row:
            cell.fill      = fill
            cell.font      = DATA_FONT
            cell.alignment = DATA_ALIGN

    # Ajuste automático de largura
    for col_idx, col_cells in enumerate(ws.columns, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = max(
            (len(str(c.value)) if c.value is not None else 0 for c in col_cells),
            default=8
        )
        ws.column_dimensions[col_letter].width = min(max_len + 3, 45)

    # Linha do cabeçalho mais alta
    ws.row_dimensions[1].height = 30

    # Congela primeira linha
    ws.freeze_panes = "A2"

    # Rodapé na célula abaixo dos dados
    rodape_row = ws.max_row + 2
    ws.cell(row=rodape_row, column=1,
            value=f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} — 11° GB PMESP")
    ws.cell(row=rodape_row, column=1).font = Font(italic=True, color="888888", size=8)

print(f"[OK] Arquivo salvo: {os.path.abspath(SAIDA)}")
