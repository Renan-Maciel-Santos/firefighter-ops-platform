# ==========================================
# IMPORTAÇÕES
# ==========================================

# Acima: Manipulação da planilha de relatório do SGP
import pandas as pd

# Acima: Helpers para batch insert/updates
from psycopg2.extras import execute_batch

# Acima: Controle de encerramento do script
import sys, os

# Acima: Permite importar _comum da raiz do projeto (compartilhado entre B1, B3 etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Acima: Helpers compartilhados dos ETLs (conexão, auditoria, parsers, localização do arquivo)
from _comum import (
    conectar_postgres,
    iniciar_etl, finalizar_etl_sucesso, finalizar_etl_erro,
    to_int, texto_ou_none, data_ptbr_para_date,
    re_para_int, normalizar_posto_grad,
    localizar_arquivo_relatorio, confirmar_com_usuario,
)


# ==========================================
# CONFIGURAÇÕES
# ==========================================

# Acima: Padrão de nome do relatório exportado pelo SGP (aba Relatórios)
PADRAO_ARQUIVO = "Relat*rio de efetivo*.xlsx"

# Acima: Tabela alvo
TABELA_EFETIVO = "b1.efetivo"

# Acima: Proteção anti-carga incompleta do relatório
MINIMO_ESPERADO = 200


# ==========================================
# FUNÇÕES AUXILIARES ESPECÍFICAS
# ==========================================

def garantir_colunas_extras(cur):
    # Acima: Adiciona (se ainda não existirem) as colunas extras disponíveis no relatório do SGP
    cur.execute(f"""
        ALTER TABLE {TABELA_EFETIVO}
          ADD COLUMN IF NOT EXISTS quadro varchar,
          ADD COLUMN IF NOT EXISTS sexo varchar(1),
          ADD COLUMN IF NOT EXISTS data_admissao date,
          ADD COLUMN IF NOT EXISTS opm_atual varchar,
          ADD COLUMN IF NOT EXISTS opm_efetiva varchar,
          ADD COLUMN IF NOT EXISTS cod_opm_efetiva integer,
          ADD COLUMN IF NOT EXISTS situacao varchar,
          ADD COLUMN IF NOT EXISTS re_dv varchar(1);
    """)


def digito_do_re(re_texto):
    # Acima: Guarda o dígito verificador ("900410-3" -> "3", "900295-A" -> "A").
    # Documento oficial (ex: a OS do EAP) cita o RE completo, e o dígito não sai de conta nenhuma.
    texto = texto_ou_none(re_texto)
    if texto is None or "-" not in texto:
        return None
    dv = texto.split("-", 1)[1].strip().upper()
    return dv[:1] or None


# ==========================================
# LOCALIZAÇÃO E LEITURA DO RELATÓRIO
# ==========================================

# Acima: Aceita um caminho explícito por argumento (opcional); senão, busca em Downloads
caminho_arg = sys.argv[1] if len(sys.argv) > 1 else None

# Acima: Resolve o arquivo a ser processado
arquivo_relatorio = localizar_arquivo_relatorio(PADRAO_ARQUIVO, caminho_arg)

# Acima: Confirma com o usuário qual arquivo será usado
confirmar_com_usuario(arquivo_relatorio)

# Acima: Lê a planilha; usa engine 'calamine' pois este relatório do SGP quebra o openpyxl (stylesheet inválido)
df = pd.read_excel(arquivo_relatorio, engine="calamine")

# Acima: Confere se a planilha tem as 12 colunas esperadas do relatório do SGP
if df.shape[1] < 12:
    print(f"❌ Planilha com formato inesperado ({df.shape[1]} colunas). Abortando.")
    sys.exit(1)

# Acima: Renomeia por posição (o SGP exporta cabeçalhos com acentuação corrompida em alguns leitores)
df.columns = [
    "numero", "re", "posto_grad", "nome", "quadro", "sexo",
    "data_admissao", "opm_atual", "cod_opm_atual",
    "opm_efetiva", "cod_opm_efetiva", "situacao"
] + list(df.columns[12:])

# Acima: Log de quantidade de linhas encontradas na planilha
print(f"🔎 Linhas na planilha: {len(df)}")


# ==========================================
# CAPTURA EFETIVO DA PLANILHA
# ==========================================

# Acima: Lista de registros capturados
registros_planilha = []

# Acima: Itera sobre cada linha da planilha
for _, linha in df.iterrows():
    # Acima: Converte RE (remove dígito verificador após o hífen)
    re_int = re_para_int(linha["re"])

    # Acima: Se RE inválido, ignora a linha
    if re_int is None:
        continue

    # Acima: Adiciona registro padronizado
    registros_planilha.append({
        "re": re_int,
        "nome": texto_ou_none(linha["nome"]),
        "posto_grad": normalizar_posto_grad(linha["posto_grad"]),
        "cod_opm_atual": to_int(linha["cod_opm_atual"]),
        "quadro": texto_ou_none(linha["quadro"]),
        "sexo": texto_ou_none(linha["sexo"]),
        "data_admissao": data_ptbr_para_date(linha["data_admissao"]),
        "opm_atual": texto_ou_none(linha["opm_atual"]),
        "opm_efetiva": texto_ou_none(linha["opm_efetiva"]),
        "cod_opm_efetiva": to_int(linha["cod_opm_efetiva"]),
        "situacao": texto_ou_none(linha["situacao"]),
        "re_dv": digito_do_re(linha["re"]),
    })

# Acima: Loga quantidade final capturada
print(f"✅ Capturados da planilha: {len(registros_planilha)}")


# ==========================================
# PROTEÇÃO CONTRA CARGA INCOMPLETA
# ==========================================

# Acima: Aborta caso a captura seja suspeita (evita inativar geral)
if len(registros_planilha) < MINIMO_ESPERADO:
    print(
        f"❌ Captura suspeita (apenas {len(registros_planilha)}). "
        f"Abaixo do mínimo {MINIMO_ESPERADO}. Abortando para não inativar indevidamente."
    )
    sys.exit(1)


# ==========================================
# SINCRONIZAÇÃO NO POSTGRES (UPSERT + INATIVA)
# ==========================================

# Acima: Conecta no Postgres containerizado
conn = conectar_postgres()

# Acima: Cria cursor
cur = conn.cursor()

# Acima: Inicializa métricas
linhas_lidas = len(registros_planilha)
linhas_inseridas = 0
linhas_atualizadas = 0
inativados = 0

# Acima: ID do ETL para auditoria
etl_id = None

try:
    # Acima: Cria/atualiza registro running na tabela b1.etl_status
    etl_id = iniciar_etl(cur, "efetivo")

    # Acima: Garante colunas extras trazidas pelo relatório (idempotente)
    garantir_colunas_extras(cur)

    # Acima: SQL de upsert (colunas originais + extras do relatório)
    sql_upsert = f"""
        INSERT INTO {TABELA_EFETIVO}
          (re, nome, posto_grad, cod_opm_atual, quadro, sexo, data_admissao,
           opm_atual, opm_efetiva, cod_opm_efetiva, situacao, re_dv, ativo, atualizado_em)
        VALUES
          (%(re)s, %(nome)s, %(posto_grad)s, %(cod_opm_atual)s, %(quadro)s, %(sexo)s, %(data_admissao)s,
           %(opm_atual)s, %(opm_efetiva)s, %(cod_opm_efetiva)s, %(situacao)s, %(re_dv)s, true, now())
        ON CONFLICT (re)
        DO UPDATE SET
          nome = EXCLUDED.nome,
          posto_grad = EXCLUDED.posto_grad,
          cod_opm_atual = EXCLUDED.cod_opm_atual,
          quadro = EXCLUDED.quadro,
          sexo = EXCLUDED.sexo,
          data_admissao = EXCLUDED.data_admissao,
          opm_atual = EXCLUDED.opm_atual,
          opm_efetiva = EXCLUDED.opm_efetiva,
          cod_opm_efetiva = EXCLUDED.cod_opm_efetiva,
          situacao = EXCLUDED.situacao,
          re_dv = COALESCE(EXCLUDED.re_dv, b1.efetivo.re_dv),
          ativo = true,
          atualizado_em = now();
    """

    # Acima: Executa em lote (reduz roundtrips ao DB)
    execute_batch(cur, sql_upsert, registros_planilha, page_size=500)

    # Acima: Conta processadas como atualizadas (métrica aproximada — UPSERT mistura insert/update)
    linhas_atualizadas = len(registros_planilha)

    # Acima: Inativa quem está ativo no banco e não apareceu na planilha
    cur.execute(f"SELECT re FROM {TABELA_EFETIVO} WHERE ativo = true;")
    re_ativos_db = set(int(x[0]) for x in cur.fetchall())
    re_planilha = set(int(r["re"]) for r in registros_planilha)
    re_sairam = list(re_ativos_db - re_planilha)

    if re_sairam:
        cur.execute(
            f"""
            UPDATE {TABELA_EFETIVO}
            SET ativo = false, atualizado_em = now()
            WHERE re = ANY(%s);
            """,
            (re_sairam,)
        )
        inativados = cur.rowcount

    # Acima: Snapshot histórico do efetivo — 1 linha por militar ativo/data
    # Acima: Permite relatórios trimestrais/semestrais com corte temporal ("efetivo em Q1")
    cur.execute("""
        INSERT INTO b1.efetivo_snapshot_mensal
          (data_referencia, re, nome, posto_grad, quadro, lotacao,
           cod_opm_atual, opm_efetiva, situacao)
        SELECT
            CURRENT_DATE, e.re, e.nome, e.posto_grad, e.quadro, v.lotacao,
            e.cod_opm_atual, e.opm_efetiva, e.situacao
        FROM b1.efetivo e
        LEFT JOIN b1.vw_efetivo_classificado v ON v.re = e.re
        WHERE e.ativo = true
        ON CONFLICT (data_referencia, re) DO UPDATE SET
          nome = EXCLUDED.nome,
          posto_grad = EXCLUDED.posto_grad,
          quadro = EXCLUDED.quadro,
          lotacao = EXCLUDED.lotacao,
          cod_opm_atual = EXCLUDED.cod_opm_atual,
          opm_efetiva = EXCLUDED.opm_efetiva,
          situacao = EXCLUDED.situacao;
    """)
    snap_gravados = cur.rowcount

    # Acima: Quantitativo do dia (b1.efetivo_quantitativo_diario). Apaga o dia e
    # regrava a partir do snapshot: um posto que zerou entre uma carga e outra
    # do mesmo dia não pode ficar com a contagem antiga.
    cur.execute("DELETE FROM b1.efetivo_quantitativo_diario WHERE data_referencia = CURRENT_DATE")
    cur.execute("""
        INSERT INTO b1.efetivo_quantitativo_diario (data_referencia, lotacao, posto_grad, quantidade)
        SELECT data_referencia,
               COALESCE(lotacao, 'SEM LOTAÇÃO'),
               COALESCE(posto_grad, 'SEM POSTO'),
               count(*)
          FROM b1.efetivo_snapshot_mensal
         WHERE data_referencia = CURRENT_DATE
         GROUP BY 1, 2, 3;
    """)

    # Acima: Finaliza ETL e commita
    finalizar_etl_sucesso(cur, etl_id, linhas_lidas, linhas_inseridas, linhas_atualizadas)
    conn.commit()

    print("\n✅ Atualização concluída.")
    print(f"📥 Linhas lidas: {linhas_lidas}")
    print(f"🔁 UPSERT (linhas processadas): {linhas_atualizadas}")
    print(f"📴 Inativados: {inativados}")
    print(f"📸 Snapshot histórico (b1.efetivo_snapshot_mensal): {snap_gravados} registros")

except Exception as e:
    conn.rollback()

    # Acima: Tenta registrar erro no ETL em uma nova transação
    try:
        if etl_id is not None:
            cur2 = conn.cursor()
            finalizar_etl_erro(cur2, etl_id, str(e))
            conn.commit()
            cur2.close()
    except:
        pass

    print("\n❌ Falha na atualização. ROLLBACK executado.")
    print("Erro:", e)

finally:
    try:
        cur.close()
    except:
        pass
    try:
        conn.close()
    except:
        pass
