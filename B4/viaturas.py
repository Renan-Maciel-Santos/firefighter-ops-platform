# ==========================================
# IMPORTAÇÕES
# ==========================================

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime
import os


# ==========================================
# CONFIGURAÇÕES
# ==========================================

# Acima: Caminho da planilha na rede interna
ARQUIVO_XLSX = r"\\servidor\compartilhado\11GB\11GBMOTOMEC\2026\V\VTRS 11º GB\Viaturas do 11GB.xlsx"

# Acima: Conexão PostgreSQL (padrão do projeto)
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

# Acima: Tabela destino
TABELA = "b4.viaturas"

# Acima: Domínio para auditoria ETL
DOMINIO = "b4_viaturas"

# Acima: Nome do lote (arquivo + timestamp)
LOTE = f"{os.path.basename(ARQUIVO_XLSX)}__{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

# Acima: Linha do cabeçalho real na planilha (0-indexed)
# Acima: Linha 0 = título "PLANILHA GERAL DAS VIATURAS..."
# Acima: Linha 1 = cabeçalho real com os nomes das colunas
LINHA_CABECALHO = 1

# Acima: Mapeamento status raw → status normalizado
STATUS_MAP = {
    "OPERANDO":          "OPERANDO",
    "BAIXADA":           "BAIXADA",
    "BAIXADA *":         "BAIXADA_DESCARGA",   # em processo de descarga
    "BAIXADA*":          "BAIXADA_DESCARGA",   # sem espaço
    "PROC. DESCARGA":    "PROC_DESCARGA",
    "PROC.DESCARGA":     "PROC_DESCARGA",
}


# ==========================================
# FUNÇÃO DE CONEXÃO
# ==========================================

def conectar_postgres():
    dsn = (
        f"host={PG_HOST} "
        f"port={PG_PORT} "
        f"dbname={PG_DB} "
        f"user={PG_USER} "
        f"password={PG_PASS}"
    )
    conn = psycopg2.connect(dsn=dsn, options="-c client_encoding=UTF8")
    conn.autocommit = False
    return conn


# ==========================================
# FUNÇÕES AUXILIARES DE LIMPEZA
# ==========================================

def limpar_texto(valor):
    # Acima: Retorna None para nulos e strings vazias
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    return texto if texto and texto.upper() not in ("NAN", "NONE", "#VALUE!", "N/P") else None


def limpar_int(valor):
    # Acima: Converte para int, retorna None se inválido
    # Acima: try/except no isna para lidar com tipos não-escalares
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    try:
        texto = str(valor).strip()
        # Acima: Descarta strings que claramente não são anos
        if not texto or texto.lower() in ("nan", "none", "n/p", "n/a", "", ".", "#value!"):
            return None
        resultado = int(float(texto))
        # Acima: Garante range válido para anos de fabricação (1900–2100)
        # Acima: Impede que RENAVAM, patrimônio e outros números grandes passem
        if resultado < 1900 or resultado > 2100:
            return None
        return resultado
    except:
        return None
    
def none_se_nan(valor):
    # Acima: Garante que float NaN do pandas vira None antes de enviar ao banco
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    return valor    


def normalizar_status(valor_raw):
    # Acima: Normaliza o status para valores controlados
    try:
        if pd.isna(valor_raw):
            return None
    except (TypeError, ValueError):
        pass
    texto = str(valor_raw).strip().upper()
    for chave, normalizado in STATUS_MAP.items():
        if texto == chave.upper():
            return normalizado
    return texto


# ==========================================
# FUNÇÕES ETL (padrão do projeto)
# ==========================================

def iniciar_etl(cur, dominio):
    cur.execute("""
        INSERT INTO b1.etl_status
            (dominio, status, iniciado_em, finalizado_em,
             linhas_lidas, linhas_inseridas, linhas_atualizadas, erro)
        VALUES (%s, 'running', now(), NULL, 0, 0, 0, NULL)
        ON CONFLICT (dominio)
        DO UPDATE SET
            status             = 'running',
            iniciado_em        = now(),
            finalizado_em      = NULL,
            linhas_lidas       = 0,
            linhas_inseridas   = 0,
            linhas_atualizadas = 0,
            erro               = NULL
        RETURNING id;
    """, (dominio,))
    return cur.fetchone()[0]


def finalizar_etl_sucesso(cur, etl_id, lidas, inseridas, atualizadas):
    cur.execute("""
        UPDATE b1.etl_status SET
            status             = 'success',
            finalizado_em      = now(),
            linhas_lidas       = %s,
            linhas_inseridas   = %s,
            linhas_atualizadas = %s,
            erro               = NULL
        WHERE id = %s;
    """, (lidas, inseridas, atualizadas, etl_id))


def finalizar_etl_erro(cur, etl_id, mensagem):
    cur.execute("""
        UPDATE b1.etl_status SET
            status        = 'error',
            finalizado_em = now(),
            erro          = %s
        WHERE id = %s;
    """, (mensagem, etl_id))


# ==========================================
# LEITURA E NORMALIZAÇÃO DO EXCEL
# ==========================================

print(f"📂 Lendo arquivo: {ARQUIVO_XLSX}")
print(f"🏷️  Lote: {LOTE}")

df = pd.read_excel(
    ARQUIVO_XLSX,
    sheet_name="Planilha1",
    header=LINHA_CABECALHO,
    dtype=str
)

# Acima: Remove espaços dos nomes das colunas
df.columns = [str(c).strip() for c in df.columns]

# Acima: Renomeia colunas para padrão interno
MAPA_COLUNAS = {
    df.columns[0]:       "prefixo",
    "OPMCB":             "opmcb",
    "SGB":               "sgb",
    "PB/BB":             "pb_bb",
    "NOME DA ESTAÇÃO":   "nome_estacao",
    "MUNICÍPIO":         "municipio",
    "STATUS ":           "status_raw",
    "STATUS":            "status_raw",
    "Proprietário":      "proprietario",
    "Placa":             "placa",
    "Fabricante":        "fabricante",
    "Modelo":            "modelo",
    "Tipo":              "tipo",
    "Ano Fabr.":         "ano_fabricacao",
    "Ano Mod.":          "ano_modelo",
    "Combustível":       "combustivel",
    "PATRIMONIO":        "patrimonio",
    "PATRIMONIO ESTADO": "patrimonio_estado",
    "obs":               "obs",
    "CHASSI":            "chassi",
    "RENAVAM":           "renavam",
    "RIV":               "riv",
}

df = df.rename(columns={k: v for k, v in MAPA_COLUNAS.items() if k in df.columns})

# Acima: Mantém número da linha de origem para auditoria
df["linha_origem"] = df.index + 3

# Acima: Remove linhas sem prefixo (rodapé, totais, linhas vazias)
df["prefixo"] = df["prefixo"].apply(limpar_texto)
df = df[df["prefixo"].notna()].copy()

# Acima: Remove linhas de legenda (OBS.:...)
df = df[~df["prefixo"].str.upper().str.startswith("OBS")].copy()
df = df[df["prefixo"].str.strip() != ""].copy()

print(f"✅ Linhas com prefixo válido: {len(df)}")

# Acima: Normaliza status
df["status_raw"] = df["status_raw"].apply(limpar_texto) if "status_raw" in df.columns else None
df["status"]     = df["status_raw"].apply(normalizar_status) if "status_raw" in df.columns else None

# Acima: Limpa colunas de texto
for col in ["opmcb", "sgb", "pb_bb", "nome_estacao", "municipio",
            "proprietario", "placa", "fabricante", "modelo", "tipo",
            "combustivel", "patrimonio", "patrimonio_estado",
            "chassi", "renavam", "riv", "obs"]:
    if col in df.columns:
        df[col] = df[col].apply(limpar_texto)

# Acima: Guarda o texto original do ano ANTES de virar int. Depois da conversão
# "CT" e "" viram os dois None, e é justamente a diferença entre eles que
# denuncia planilha deslocada.
df["_ano_fabr_bruto"] = df["ano_fabricacao"] if "ano_fabricacao" in df.columns else None

# Acima: Converte anos para inteiro (com validação de range 1900–2100)
df["ano_fabricacao"] = df["ano_fabricacao"].apply(limpar_int) if "ano_fabricacao" in df.columns else None
df["ano_modelo"]     = df["ano_modelo"].apply(limpar_int)     if "ano_modelo"     in df.columns else None


# ==========================================
# GUARDA: LINHAS COM COLUNAS DESLOCADAS
# ==========================================
# Em 20/08/2026 o bloco CT da planilha estava inteiro deslocado uma coluna: a
# placa caiu em "Fabricante", o fabricante em "Modelo" e o TIPO ("CT") em
# "Ano Fabr.". O ETL gravou 16 viaturas com placa, modelo, tipo e combustível
# trocados, e reclamou só do ano — o único campo com tipo forte o bastante
# para a bagunça aparecer.
#
# Dado errado é pior que dado velho: a B.I.A. responde os dois com a mesma
# confiança, e ninguém desconfia de uma placa que existe. Então a linha
# suspeita é DESCARTADA, não gravada.

def parece_ano(valor):
    """True se o texto pode ser um ano. False para 'CT', 'REBOQUE' e afins.

    Vazio conta como True: ausência de dado é problema de preenchimento, não
    de deslocamento — e some no aviso de ano nulo, logo abaixo.
    """
    try:
        if pd.isna(valor):
            return True
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "none", "n/p", "n/a", "-", "."):
        return True
    try:
        float(texto)
        return True
    except ValueError:
        return False


alinhadas = df["_ano_fabr_bruto"].apply(parece_ano)
deslocadas = df[~alinhadas].copy()
LINHAS_DESCARTADAS = len(deslocadas)

if LINHAS_DESCARTADAS:
    print("\n" + "=" * 66)
    print(f"🚨 {LINHAS_DESCARTADAS} linha(s) com COLUNAS DESLOCADAS — NÃO serão gravadas")
    print("=" * 66)
    print('   Sintoma: a coluna "Ano Fabr." contém texto que não é ano.')
    print("   Causa provável: as células da linha estão uma coluna à direita,")
    print("   então placa, fabricante, modelo e combustível também estão errados.")
    print(f"   Corrija na origem: {ARQUIVO_XLSX}\n")
    print(deslocadas[["prefixo", "linha_origem", "_ano_fabr_bruto"]]
          .rename(columns={"_ano_fabr_bruto": 'valor em "Ano Fabr."'})
          .to_string(index=False))
    print("=" * 66 + "\n")
    df = df[alinhadas].copy()

df = df.drop(columns=["_ano_fabr_bruto"])

# Acima: Adiciona coluna de lote
df["lote_importacao"] = LOTE

# Acima: PRE-FLIGHT: mostra anos que ficaram None (possíveis dados ruins)
problemas = df[["prefixo", "ano_fabricacao", "ano_modelo"]].copy()
problemas = problemas[problemas["ano_fabricacao"].isna() | problemas["ano_modelo"].isna()]
if not problemas.empty:
    print(f"⚠️  {len(problemas)} viatura(s) com ano inválido/ausente (serão inseridas com NULL):")
    print(problemas.to_string(index=False))

print(f"\n📊 Distribuição de status:")
print(df["status"].value_counts().to_string())


# ==========================================
# CARGA NO POSTGRESQL
# ==========================================

conn   = conectar_postgres()
cur    = conn.cursor()
etl_id = None

try:
    etl_id = iniciar_etl(cur, DOMINIO)
    conn.commit()

    # Acima: SQL de UPSERT — prefixo é a chave natural da viatura
    sql = f"""
        INSERT INTO {TABELA} (
            prefixo, opmcb, sgb, pb_bb, nome_estacao, municipio,
            status, status_raw, proprietario, placa,
            fabricante, modelo, tipo,
            ano_fabricacao, ano_modelo, combustivel,
            patrimonio, patrimonio_estado,
            chassi, renavam, riv, obs,
            lote_importacao, linha_origem, atualizado_em
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, now()
        )
        ON CONFLICT (prefixo)
        DO UPDATE SET
            opmcb             = EXCLUDED.opmcb,
            sgb               = EXCLUDED.sgb,
            pb_bb             = EXCLUDED.pb_bb,
            nome_estacao      = EXCLUDED.nome_estacao,
            municipio         = EXCLUDED.municipio,
            status            = EXCLUDED.status,
            status_raw        = EXCLUDED.status_raw,
            proprietario      = EXCLUDED.proprietario,
            placa             = EXCLUDED.placa,
            fabricante        = EXCLUDED.fabricante,
            modelo            = EXCLUDED.modelo,
            tipo              = EXCLUDED.tipo,
            ano_fabricacao    = EXCLUDED.ano_fabricacao,
            ano_modelo        = EXCLUDED.ano_modelo,
            combustivel       = EXCLUDED.combustivel,
            patrimonio        = EXCLUDED.patrimonio,
            patrimonio_estado = EXCLUDED.patrimonio_estado,
            chassi            = EXCLUDED.chassi,
            renavam           = EXCLUDED.renavam,
            riv               = EXCLUDED.riv,
            obs               = EXCLUDED.obs,
            lote_importacao   = EXCLUDED.lote_importacao,
            linha_origem      = EXCLUDED.linha_origem,
            atualizado_em     = now();
    """

    # Acima: Monta lista de tuplas para execute_batch
    params = []
    for row in df.itertuples(index=False):
        params.append((
            row.prefixo,
            getattr(row, "opmcb",             None),
            getattr(row, "sgb",               None),
            getattr(row, "pb_bb",             None),
            getattr(row, "nome_estacao",      None),
            getattr(row, "municipio",         None),
            getattr(row, "status",            None),
            getattr(row, "status_raw",        None),
            getattr(row, "proprietario",      None),
            getattr(row, "placa",             None),
            getattr(row, "fabricante",        None),
            getattr(row, "modelo",            None),
            getattr(row, "tipo",              None),
            none_se_nan(getattr(row, "ano_fabricacao", None)),  # ← aqui
            none_se_nan(getattr(row, "ano_modelo",     None)),  # ← e aqui
            getattr(row, "combustivel",       None),
            getattr(row, "patrimonio",        None),
            getattr(row, "patrimonio_estado", None),
            getattr(row, "chassi",            None),
            getattr(row, "renavam",           None),
            getattr(row, "riv",               None),
            getattr(row, "obs",               None),
            row.lote_importacao,
            int(row.linha_origem),
        ))

    # DEBUG — roda isso no lugar do execute_batch por enquanto
    print("🔍 Testando linha por linha...")
    for i, p in enumerate(params):
        try:
            cur.execute(sql, p)
        except Exception as e:
            print(f"\n❌ Erro na linha {i} — prefixo: {p[0]}")
            print(f"   Valores: {p}")
            print(f"   Erro: {e}")
            conn.rollback()
            break
    # Acima: Executa em lote (padrão do projeto)
    execute_batch(cur, sql, params, page_size=500)
    conn.commit()

    total = len(params)
    finalizar_etl_sucesso(cur, etl_id, total, total, total)
    conn.commit()

    print(f"\n✅ Importação concluída com sucesso.")
    print(f"📥 Viaturas processadas (UPSERT): {total}")

except Exception as e:
    conn.rollback()
    if etl_id:
        try:
            finalizar_etl_erro(cur, etl_id, str(e))
            conn.commit()
        except:
            conn.rollback()
    print(f"\n❌ Erro na importação: {e}")
    raise   # Acima: Re-raise para ver o traceback completo

finally:
    try:
        cur.close()
    except:
        pass
    try:
        conn.close()
    except:
        pass


# ==========================================
# CÓDIGO DE SAÍDA
# ==========================================
# Carga parcial sai com 2, e não com 0. O orquestrador só distingue zero de
# não-zero, então vai rotular o domínio como falha — é o efeito desejado:
# planilha deslocada precisa de gente, e um "ok" verde faz justamente ninguém
# ir olhar. As linhas boas já foram gravadas antes deste ponto.
if LINHAS_DESCARTADAS:
    print(f"⚠️  Carga PARCIAL: {LINHAS_DESCARTADAS} linha(s) deslocada(s) ficaram de fora.")
    print("   Os dados antigos delas seguem no banco, sem atualização.")
    _sys.exit(2)