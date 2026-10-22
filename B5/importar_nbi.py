"""
Importa NBI2026.xlsx → b5.elogios
Uso: python importar_nbi.py [caminho_do_xlsx]
     (padrão: a planilha viva da B5 no share, pasta 11GB5/N/NBI2026)
"""

import sys
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime

# ==========================================
# CONFIGURAÇÕES
# ==========================================

ARQUIVO = sys.argv[1] if len(sys.argv) > 1 else r"\\servidor\compartilhado\11GB\11GB5\N\NBI2026\NBI2026.xlsx"
SHEET   = "2026"

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

SGB_MAP = {
    1: "1° SGB", 2: "2° SGB", 3: "3° SGB", 4: "4° SGB",
    "1": "1° SGB", "2": "2° SGB", "3": "3° SGB", "4": "4° SGB",
    "SEDE": "SEDE", "COBOM": "SEDE", "SAT": "SEDE",
}

# ==========================================
# HELPERS
# ==========================================

def _txt(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val).strip() or None

def _int(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def _date(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, pd.Timestamp):
        return val.date() if not pd.isnull(val) else None
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    if s in ("", "NaT", "nan", "NaN"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

def _sgb(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    key = int(val) if isinstance(val, float) else val
    return SGB_MAP.get(key, str(val).strip())

def _ano(mes_ano, fallback_date=None):
    """Extrai ano de '2/2026' → 2026.
    Se o resultado for <= 1900 (erro de fórmula Excel), usa o ano da data de fallback."""
    txt = _txt(mes_ano)
    if txt:
        parts = txt.split("/")
        try:
            ano = int(parts[-1])
            if ano > 1900:
                return ano
        except (ValueError, IndexError):
            pass
    # Fallback: extrai o ano da data de concessão
    d = _date(fallback_date)
    if d:
        return d.year
    return None

# ==========================================
# LEITURA DO EXCEL
# ==========================================

print(f"[*] Lendo {ARQUIVO} …")
df = pd.read_excel(ARQUIVO, sheet_name=SHEET)

# Coluna 6 tem nome longo/corrompido — pega pelo índice
col_data_elogio = df.columns[6]


def _coluna(inicio):
    """Acha a coluna cujo cabeçalho começa por 'inicio', ignorando caixa e espaços.

    Acima: Os cabeçalhos desta planilha não são estáveis — vêm em caixa alta ('NOME',
    'ASSUNTO') e alguns carregam a instrução de uso junto do nome ('DATA DO LANÇAMENTO
    ENTRA NO CONTROLE MENSAL'). Casar por texto exato fazia a coluna virar None em
    silêncio: 711 nomes e 699 datas de lançamento entravam no banco vazios com o dado
    preenchido na origem. Casar por prefixo sobrevive a mudança de caixa e a sufixo novo.
    """
    alvo = inicio.strip().upper()
    for c in df.columns:
        if isinstance(c, str) and c.strip().upper().startswith(alvo):
            return c
    # Acima: Coluna some da planilha é erro de origem, e falhar aqui é melhor que
    # gravar a tabela inteira com a coluna nula sem ninguém perceber.
    raise SystemExit(f"❌ Coluna começando por {inicio!r} não encontrada em {ARQUIVO}")


col_nome = _coluna("NOME")
col_assunto = _coluna("ASSUNTO")
col_data_lancamento = _coluna("DATA DO LANÇAMENTO")

# Filtra apenas linhas com RE preenchido
df = df[df["RE"].notna() & (df["RE"].astype(str).str.strip() != "")]
print(f"[OK] {len(df)} registros com RE encontrados.")

# ==========================================
# CONEXÃO
# ==========================================

conn = psycopg2.connect(
    host=PG_HOST, port=PG_PORT, dbname=PG_DB,
    user=PG_USER, password=PG_PASS
)
conn.autocommit = False
cur = conn.cursor()

# ==========================================
# TRUNCATE + INSERT
# ==========================================

cur.execute("TRUNCATE b5.elogios RESTART IDENTITY;")
print("[DEL]  Tabela limpa.")

SQL = """
    INSERT INTO b5.elogios (
        nbi, num_bi_11gb, posto_grad, re, nome, assunto, tipo,
        data_elogio, sgb, data_lancamento, lancador,
        solenidade, observacoes, data_base, boletim, mes_ano, ano
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s
    )
"""

params = []
for _, r in df.iterrows():
    params.append((
        _int(r.get("NBI")),
        _int(r.get("Nº BI11GB")),
        _txt(r.get("Graduação")),
        _txt(r.get("RE")),
        _txt(r.get(col_nome)),
        _txt(r.get(col_assunto)),
        _txt(r.get("TIPO")),
        _date(r.get(col_data_elogio)),
        _sgb(r.get("SGB")),
        _date(r.get(col_data_lancamento)),
        _txt(r.get("LANÇADOR ")),
        _txt(r.get("SOLENIDADE")),
        _txt(r.get("OBSERVAÇÕES")),
        _date(r.get("DATA BASE")),
        _txt(r.get("BOLETIM")),
        _txt(r.get("MÊS/ano")),
        _ano(r.get("MÊS/ano"), fallback_date=r.get(col_data_elogio)),
    ))

execute_batch(cur, SQL, params, page_size=200)
conn.commit()

print(f"[OK] {len(params)} registros inseridos em b5.elogios.")
cur.close()
conn.close()
