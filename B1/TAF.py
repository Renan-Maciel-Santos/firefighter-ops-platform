# ==========================================
# IMPORTAÇÕES
# ==========================================

# Acima: Manipulação de planilhas e dados tabulares
import pandas as pd

# Acima: Conector PostgreSQL
import psycopg2

# Acima: Execução em lote mais performática
from psycopg2.extras import execute_batch

# Acima: Gera timestamp do lote de importação
from datetime import datetime

# Acima: Manipula caminhos e nomes de arquivo
import os


# ==========================================
# CONFIGURAÇÕES
# ==========================================

# Acima: Caminho do arquivo Excel (ajuste para o seu arquivo)
ARQUIVO_XLSX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "taf.xlsx")

# Acima: Conexão com o PostgreSQL (seu padrão local)
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

# Acima: Tabela destino RAW (guarda 100% das linhas)
TABELA_TAF_RAW = "b1.taf_resultados_raw"

# Acima: Nome do lote (mantém rastreabilidade: arquivo + data/hora)
# Acima: Exemplo: "taf.xlsx__2026-02-23_10-15-30"
LOTE_IMPORTACAO = f"{os.path.basename(ARQUIVO_XLSX)}__{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"


# ==========================================
# FUNÇÃO DE CONEXÃO
# ==========================================

def conectar_postgres():
    # Acima: Monta string DSN
    dsn = (
        f"host={PG_HOST} "
        f"port={PG_PORT} "
        f"dbname={PG_DB} "
        f"user={PG_USER} "
        f"password={PG_PASS}"
    )

    # Acima: Abre conexão forçando UTF-8
    conn = psycopg2.connect(
        dsn=dsn,
        options="-c client_encoding=UTF8"
    )

    # Acima: Desativa autocommit para controle transacional
    conn.autocommit = False

    # Acima: Retorna conexão
    return conn


# ==========================================
# FUNÇÃO DE LIMPEZA DE TEXTO
# ==========================================

def limpar_texto(valor):
    # Acima: Se for nulo, retorna None
    if pd.isna(valor):
        return None

    # Acima: Converte para string e remove espaços
    texto = str(valor).strip()

    # Acima: Se vazio, retorna None
    if texto == "":
        return None

    # Acima: Retorna texto limpo
    return texto


# ==========================================
# LEITURA DO EXCEL (RAW: SEM DEDUP)
# ==========================================

# Acima: Lê a primeira aba do Excel
df = pd.read_excel(
    ARQUIVO_XLSX,
    sheet_name=0
)

# Acima: Garante que retornou DataFrame
if not isinstance(df, pd.DataFrame):
    raise TypeError("O arquivo não retornou um DataFrame válido.")

# Acima: Remove espaços dos nomes das colunas
df.columns = [str(c).strip() for c in df.columns]

# Acima: Mapeia colunas do Excel para padrão do banco
# Acima: Ajuste aqui caso algum nome venha diferente no seu arquivo
mapa_colunas = {
    "RE": "re",
    "Status": "status",
    "Resultado": "resultado",
    "tipo_taf": "tipo_taf",
    "data_realizado": "data_realizado",
}

# Acima: Renomeia colunas
df = df.rename(columns=mapa_colunas)

# Acima: Valida colunas mínimas (RAW precisa pelo menos do RE para ser útil)
colunas_minimas = ["re"]

for col in colunas_minimas:
    # Acima: Se coluna não existir, aborta
    if col not in df.columns:
        raise ValueError(f"Coluna mínima não encontrada no Excel: {col}")

# Acima: Mantém o número da linha de origem (linha do Excel) para rastreabilidade
# Acima: Considerando que a primeira linha do Excel é cabeçalho, os dados começam na linha 2
df["linha_origem"] = df.index + 2

# Acima: Limpa textos (sem derrubar linhas)
df["status"] = df["status"].apply(limpar_texto) if "status" in df.columns else None
df["resultado"] = df["resultado"].apply(limpar_texto) if "resultado" in df.columns else None
df["tipo_taf"] = df["tipo_taf"].apply(limpar_texto) if "tipo_taf" in df.columns else None

# Acima: Converte RE para numérico (inválidos viram NaN)
df["re"] = pd.to_numeric(df["re"], errors="coerce")

# Acima: Remove apenas linhas sem RE (sem RE não dá para cruzar com efetivo)
df = df[df["re"].notna()]

# Acima: Converte RE para int
df["re"] = df["re"].astype(int)

# Acima: Converte data no padrão brasileiro dd/mm/yyyy (mantém None se inválido, não derruba linha)
if "data_realizado" in df.columns:
    # Acima: Tenta converter para datetime
    df["data_realizado"] = pd.to_datetime(
        df["data_realizado"],
        errors="coerce",
        dayfirst=True
    )

    # Acima: Converte datetime para date (mantém NaT como NaT/NaN e depois vira None nos params)
    df["data_realizado"] = df["data_realizado"].dt.date

# Acima: Log quantidade final que será inserida na RAW
print(f"✅ Linhas que serão inseridas na RAW: {len(df)}")
print(f"🏷️ Lote de importação: {LOTE_IMPORTACAO}")


# ==========================================
# CARGA NO POSTGRES (RAW: INSERT PURO)
# ==========================================

# Acima: Abre conexão
conn = conectar_postgres()

# Acima: Cria cursor
cur = conn.cursor()

try:
    # Acima: SQL de INSERT na tabela RAW (sem ON CONFLICT, sem deduplicar)
    sql_insert = f"""
        insert into {TABELA_TAF_RAW} (
            re,
            status,
            resultado,
            tipo_taf,
            data_realizado,
            lote_importacao,
            linha_origem
        )
        values (
            %s, %s, %s, %s, %s, %s, %s
        );
    """

    # Acima: Monta lista de parâmetros na ordem do INSERT
    # Acima: Usa .get() para evitar KeyError caso coluna não exista
    params = [
        (
            int(row.re),
            row.status if "status" in df.columns else None,
            row.resultado if "resultado" in df.columns else None,
            row.tipo_taf if "tipo_taf" in df.columns else None,
            row.data_realizado if "data_realizado" in df.columns else None,
            LOTE_IMPORTACAO,
            int(row.linha_origem)
        )
        for row in df.itertuples(index=False)
    ]

    # Acima: Executa em lote para performance
    execute_batch(cur, sql_insert, params, page_size=1000)

    # Acima: Confirma transação
    conn.commit()

    # Acima: Log de sucesso
    print("✅ Importação RAW concluída com sucesso.")
    print(f"📥 Inseridas na RAW: {len(params)}")

except Exception as e:
    # Acima: Desfaz transação em caso de erro
    conn.rollback()

    # Acima: Loga o erro
    print("❌ Erro na importação RAW:", e)

finally:
    # Acima: Fecha cursor
    try:
        cur.close()
    except:
        pass

    # Acima: Fecha conexão
    try:
        conn.close()
    except:
        pass