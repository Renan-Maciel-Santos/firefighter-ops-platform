"""
Importa CONTROLE DE PROCESSOS UGE 990210 - ANO.xlsx → uge.processos
Uso: python importar_uge.py [caminho_xlsx] [ano]
"""

import sys
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime

# ==========================================
ARQUIVO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CONTROLE DE PROCESSOS UGE 990210 - 2026.xlsx")
ANO     = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
SHEET   = f"PROCESSOS UGE-990210 - {ANO}"

# Acima: Credenciais vêm do .env da raiz — nunca do fonte, que é versionado
import os as _os, sys as _sys
_sys.path.append(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from _env import exigir, opcional

PG_HOST = opcional("PG_HOST", "localhost")
PG_PORT = int(opcional("PG_PORT", "5432"))
PG_DB   = opcional("PG_DB", "11gb")
PG_USER = opcional("PG_USER", "admin")
PG_PASS = exigir("PG_PASS")

# ==========================================
def _txt(v):
    if v is None: return None
    try:
        if pd.isna(v): return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s if s and s.lower() not in ('nan', 'nat') else None

def _num(v):
    if v is None: return None
    try:
        if pd.isna(v): return None
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def _int(v):
    n = _num(v)
    return int(n) if n is not None else None

def _date(v):
    if v is None: return None
    try:
        if pd.isna(v): return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp): return v.date() if not pd.isnull(v) else None
    if isinstance(v, datetime):    return v.date()
    s = str(v).strip()
    if not s or s.lower() in ('nan', 'nat'): return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try: return datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

# ==========================================
print(f"[*] Lendo {ARQUIVO} (aba: {SHEET}) ...")
df = pd.read_excel(ARQUIVO, sheet_name=SHEET, header=6)
# Tenta detectar se a coluna PENDÊNCIA já existe (procura nas primeiras 22 colunas)
df_full = df.copy()
df = df.iloc[:, 1:21]  # 20 colunas base
df.columns = [
    'num', 'sei', 'siafem', 'licitacao', 'solicitante', 'objeto', 'classe',
    'ptres', 'nd', 'fonte', 'ne', 'empenhado', 'entrega_emp', 'ok1',
    'entrega_prorr', 'ok2', 'liquidado', 'observacoes', 'responsavel', 'status'
]
# Procura coluna "PENDÊNCIA" / "PENDENCIA" em qualquer posição
df['pendencia'] = None
for c in df_full.columns:
    nome = str(c).strip().upper()
    if 'PEND' in nome and len(nome) <= 20:
        df['pendencia'] = df_full[c].values
        print(f"[INFO] Coluna de pendencia encontrada: {repr(c)}")
        break

# Mantém só linhas com número E processo SEI (filtra placeholders vazios)
df = df[df['num'].apply(lambda x: isinstance(x, (int, float)) and pd.notna(x))]
df = df[df['sei'].apply(lambda x: pd.notna(x) and str(x).strip() != '')]
print(f"[OK] {len(df)} processos validos encontrados.")

# ==========================================
conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS)
conn.autocommit = False
cur = conn.cursor()

cur.execute("DELETE FROM uge.processos WHERE ano = %s;", (ANO,))
print(f"[DEL] Removidos processos antigos do ano {ANO}.")

SQL = """
INSERT INTO uge.processos (
    numero, processo_sei, processo_siafem, licitacao, solicitante,
    objeto, classe, ptres, nd, fonte, ne,
    valor_empenhado, entrega_empenhada, ok_empenho,
    entrega_prorrogada, ok_prorrog,
    valor_liquidado, observacoes, responsavel, status, pendencia, ano
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s,
    %s, %s, %s, %s, %s, %s
)
"""

params = []
for _, r in df.iterrows():
    params.append((
        _int(r['num']),
        _txt(r['sei']),
        _txt(r['siafem']),
        _txt(r['licitacao']),
        _txt(r['solicitante']),
        _txt(r['objeto']),
        _txt(r['classe']),
        _txt(r['ptres']),
        _txt(r['nd']),
        _txt(r['fonte']),
        _txt(r['ne']),
        _num(r['empenhado']),
        _date(r['entrega_emp']),
        _txt(r['ok1']),
        _date(r['entrega_prorr']),
        _txt(r['ok2']),
        _num(r['liquidado']),
        _txt(r['observacoes']),
        _txt(r['responsavel']),
        _txt(r['status']),
        _txt(r['pendencia']),
        ANO,
    ))

execute_batch(cur, SQL, params, page_size=200)
conn.commit()
print(f"[OK] {len(params)} processos inseridos em uge.processos.")
cur.close()
conn.close()
