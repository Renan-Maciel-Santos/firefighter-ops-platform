# ==========================================
# IMPORTAÇÕES
# ==========================================

# Acima: Manipulação da planilha do relatório de IAS do SGP
import pandas as pd

# Acima: Helpers para batch insert/updates
from psycopg2.extras import execute_batch

# Acima: Controle de encerramento do script
import sys, os

# Acima: Permite importar _comum da raiz do projeto (compartilhado entre B1, B3 etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Acima: Helpers compartilhados dos ETLs
from _comum import (
    conectar_postgres,
    iniciar_etl, finalizar_etl_sucesso, finalizar_etl_erro,
    to_int, texto_ou_none, data_ptbr_para_date, re_para_int,
    localizar_arquivo_relatorio, confirmar_com_usuario,
)


# ==========================================
# CONFIGURAÇÕES
# ==========================================

# Acima: Padrão de nome do relatório exportado pelo SGP (tela Relação de Inspeções)
PADRAO_ARQUIVO = "tabelaRelacaoInspec*.xlsx"

# Acima: Tabela de IAS
TABELA_IAS = "b1.ias_inspecao"

# Acima: Proteção anti-carga incompleta
MINIMO_ESPERADO = 200


# ==========================================
# FUNÇÕES AUXILIARES ESPECÍFICAS
# ==========================================

def garantir_coluna_situacao(cur):
    # Acima: Adiciona a coluna trazida pelo relatório (idempotente)
    cur.execute(f"""
        ALTER TABLE {TABELA_IAS}
          ADD COLUMN IF NOT EXISTS situacao_inspecao varchar,
          ADD COLUMN IF NOT EXISTS atualizado_em timestamptz;
    """)


def extrair_ano_do_processo(numero_processo):
    # Acima: Número do processo tem o formato IASNNXXXXXXX, onde NN são os 2 últimos dígitos do ano
    processo = texto_ou_none(numero_processo)

    # Acima: Sem processo, sem ano
    if processo is None:
        return None

    # Acima: Se não bate o padrão mínimo (IAS + 2 dígitos), aborta
    if not processo.upper().startswith("IAS") or len(processo) < 5:
        return None

    # Acima: Extrai os 2 dígitos após "IAS" e converte para ano completo (2000 + NN)
    try:
        return 2000 + int(processo[3:5])
    except:
        return None


# ==========================================
# LOCALIZAÇÃO E LEITURA DO RELATÓRIO
# ==========================================

# Acima: Aceita um caminho explícito por argumento (opcional); senão, busca em Downloads
caminho_arg = sys.argv[1] if len(sys.argv) > 1 else None

# Acima: Resolve o arquivo a ser processado
arquivo_relatorio = localizar_arquivo_relatorio(PADRAO_ARQUIVO, caminho_arg)

# Acima: Confirma com o usuário
confirmar_com_usuario(arquivo_relatorio)

# Acima: Lê a planilha; usa engine 'calamine' pois relatórios do SGP quebram o openpyxl
df = pd.read_excel(arquivo_relatorio, engine="calamine")

# Acima: Confere se a planilha tem as 14 colunas esperadas do relatório de inspeção
if df.shape[1] < 14:
    print(f"❌ Planilha com formato inesperado ({df.shape[1]} colunas). Abortando.")
    sys.exit(1)

# Acima: Renomeia por posição (o SGP exporta cabeçalhos com acentuação corrompida)
df.columns = [
    "opm", "posto_grad", "re", "nome", "data_nascimento",
    "data_inspecao_medica", "data_inspecao_odontologica", "data_validade",
    "numero_processo", "situacao_inspecao",
    "inspecao_medica", "inspecao_odontologica",
    "parecer_medico_taf", "parecer_medico_tat"
] + list(df.columns[14:])

# Acima: Log de quantidade de linhas encontradas na planilha
print(f"🔎 Linhas na planilha: {len(df)}")


# ==========================================
# CAPTURA IAS DA PLANILHA
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

    # Acima: Extrai o número do processo (chave da IAS)
    numero_processo = texto_ou_none(linha["numero_processo"])

    # Acima: Sem número do processo não é possível deduplicar / gravar
    if numero_processo is None:
        continue

    # Acima: Monta registro alinhado com a tabela b1.ias_inspecao
    registros_planilha.append({
        "re": re_int,
        "ano": extrair_ano_do_processo(numero_processo),
        "numero_processo": numero_processo,
        "data_inspecao_medica": data_ptbr_para_date(linha["data_inspecao_medica"]),
        "data_inspecao_odontologica": data_ptbr_para_date(linha["data_inspecao_odontologica"]),
        "data_validade": data_ptbr_para_date(linha["data_validade"]),
        "inspecao_medica": texto_ou_none(linha["inspecao_medica"]),
        "inspecao_odontologica": texto_ou_none(linha["inspecao_odontologica"]),
        "parecer_medico_taf": texto_ou_none(linha["parecer_medico_taf"]),
        "parecer_medico_tat": texto_ou_none(linha["parecer_medico_tat"]),
        "situacao_inspecao": texto_ou_none(linha["situacao_inspecao"]),
    })

# Acima: Loga quantidade final capturada
print(f"✅ Capturados da planilha: {len(registros_planilha)}")


# ==========================================
# PROTEÇÃO CONTRA CARGA INCOMPLETA
# ==========================================

# Acima: Aborta caso a captura seja suspeita
if len(registros_planilha) < MINIMO_ESPERADO:
    print(
        f"❌ Captura suspeita (apenas {len(registros_planilha)}). "
        f"Abaixo do mínimo {MINIMO_ESPERADO}. Abortando."
    )
    sys.exit(1)


# ==========================================
# SINCRONIZAÇÃO NO POSTGRES (UPSERT)
# ==========================================

# Acima: Conecta no Postgres containerizado
conn = conectar_postgres()

# Acima: Cria cursor
cur = conn.cursor()

# Acima: Inicializa métricas
linhas_lidas = len(registros_planilha)
linhas_inseridas = 0
linhas_atualizadas = 0

# Acima: ID do ETL para auditoria
etl_id = None

try:
    # Acima: Cria/atualiza registro running na tabela b1.etl_status
    etl_id = iniciar_etl(cur, "ias")

    # Acima: Adiciona colunas novas se ainda não existirem (idempotente)
    garantir_coluna_situacao(cur)

    # Acima: SQL de upsert; usa COALESCE para não sobrescrever com NULL o que já está no banco
    # Acima: (o histórico é imutável, mas situacao_inspecao muda com o tempo — expirar)
    sql_upsert = f"""
        INSERT INTO {TABELA_IAS}
          (re, ano, numero_processo,
           data_inspecao_medica, data_inspecao_odontologica, data_validade,
           inspecao_medica, inspecao_odontologica,
           parecer_medico_taf, parecer_medico_tat,
           situacao_inspecao, atualizado_em)
        VALUES
          (%(re)s, %(ano)s, %(numero_processo)s,
           %(data_inspecao_medica)s, %(data_inspecao_odontologica)s, %(data_validade)s,
           %(inspecao_medica)s, %(inspecao_odontologica)s,
           %(parecer_medico_taf)s, %(parecer_medico_tat)s,
           %(situacao_inspecao)s, now())
        ON CONFLICT (re, ano, numero_processo)
        DO UPDATE SET
          data_inspecao_medica = COALESCE(EXCLUDED.data_inspecao_medica, {TABELA_IAS}.data_inspecao_medica),
          data_inspecao_odontologica = COALESCE(EXCLUDED.data_inspecao_odontologica, {TABELA_IAS}.data_inspecao_odontologica),
          data_validade = COALESCE(EXCLUDED.data_validade, {TABELA_IAS}.data_validade),
          inspecao_medica = COALESCE(EXCLUDED.inspecao_medica, {TABELA_IAS}.inspecao_medica),
          inspecao_odontologica = COALESCE(EXCLUDED.inspecao_odontologica, {TABELA_IAS}.inspecao_odontologica),
          parecer_medico_taf = COALESCE(EXCLUDED.parecer_medico_taf, {TABELA_IAS}.parecer_medico_taf),
          parecer_medico_tat = COALESCE(EXCLUDED.parecer_medico_tat, {TABELA_IAS}.parecer_medico_tat),
          situacao_inspecao = COALESCE(EXCLUDED.situacao_inspecao, {TABELA_IAS}.situacao_inspecao),
          atualizado_em = now();
    """

    # Acima: Contagem antes/depois para medir inseridos (novas IASs) x atualizados
    cur.execute(f"SELECT count(*) FROM {TABELA_IAS};")
    total_antes = cur.fetchone()[0]

    execute_batch(cur, sql_upsert, registros_planilha, page_size=500)

    cur.execute(f"SELECT count(*) FROM {TABELA_IAS};")
    total_depois = cur.fetchone()[0]

    linhas_inseridas = total_depois - total_antes
    linhas_atualizadas = len(registros_planilha) - linhas_inseridas

    # Acima: Finaliza ETL e commita
    finalizar_etl_sucesso(cur, etl_id, linhas_lidas, linhas_inseridas, linhas_atualizadas)
    conn.commit()

    print("\n✅ Atualização concluída.")
    print(f"📥 Linhas lidas: {linhas_lidas}")
    print(f"➕ Inseridos (IASs novas): {linhas_inseridas}")
    print(f"🔁 Atualizados (situação/datas): {linhas_atualizadas}")

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
