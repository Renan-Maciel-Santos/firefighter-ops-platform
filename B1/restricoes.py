# ==========================================
# IMPORTAÇÕES
# ==========================================

# Acima: Manipulação da planilha de relatório de Restrições do SGP
import pandas as pd

# Acima: Helpers para batch insert
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

# Acima: Padrão de nome do relatório exportado pelo SGP
PADRAO_ARQUIVO = "Relat*rio Restri*.xlsx"

# Acima: Tabela alvo (schema novo, substituiu b1.restricoes_homologacoes)
TABELA_RESTRICOES = "b1.restricoes"

# Acima: Tabelas legadas do fluxo Selenium (removidas no primeiro import)
TABELA_ANTIGA = "b1.restricoes_homologacoes"

# Acima: Proteção anti-arquivo vazio/corrompido (baixo porque a query por OPM traz só vigentes,
# e o modelo é incremental — nunca apaga dado existente)
MINIMO_ESPERADO = 1


# ==========================================
# FUNÇÕES AUXILIARES ESPECÍFICAS
# ==========================================

def preparar_schema(cur):
    # Acima: Remove tabelas legadas do fluxo antigo (Selenium/perícias)
    cur.execute(f"DROP TABLE IF EXISTS {TABELA_ANTIGA};")
    cur.execute("DROP TABLE IF EXISTS b1.etl_status_re;")
    cur.execute("DROP TABLE IF EXISTS b1.coleta_falhas;")

    # Acima: Cria a nova tabela de restrições (schema alinhado ao relatório do SGP)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABELA_RESTRICOES} (
          id bigserial primary key,
          re integer not null,
          condicao varchar,
          restricao_medica text,
          origem varchar,
          data_inicial date not null,
          data_final date,
          total_dias integer,
          observacao varchar,
          atualizado_em timestamptz not null default now()
        );
    """)

    # Acima: Índices úteis para consultas do painel
    cur.execute(f"CREATE INDEX IF NOT EXISTS ix_restricoes_re ON {TABELA_RESTRICOES} (re);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS ix_restricoes_data_final ON {TABELA_RESTRICOES} (data_final);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS ix_restricoes_observacao ON {TABELA_RESTRICOES} (observacao);")

    # Acima: Índice composto pra acelerar a checagem "essa restrição já existe?" no INSERT
    # Acima: (re, origem, data_inicial) é a chave natural — juntos identificam uma restrição do SGP
    cur.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_restricoes_natural
        ON {TABELA_RESTRICOES} (re, origem, data_inicial);
    """)


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

# Acima: Confere se a planilha tem as 12 colunas esperadas do relatório de restrições
if df.shape[1] < 12:
    print(f"❌ Planilha com formato inesperado ({df.shape[1]} colunas). Abortando.")
    sys.exit(1)

# Acima: Renomeia por posição (o SGP exporta cabeçalhos com acentuação corrompida)
# Acima: Quadro/Posto/Grad/Nome/OPM Efetiva vem via JOIN com b1.efetivo — só o RE é preservado
df.columns = [
    "quadro", "posto_grad", "re", "nome", "opm_efetiva",
    "condicao", "restricao_medica", "origem",
    "data_inicial", "data_final", "total_dias", "observacao"
] + list(df.columns[12:])

# Acima: Log de quantidade de linhas encontradas na planilha
print(f"🔎 Linhas na planilha: {len(df)}")


# ==========================================
# CAPTURA DAS RESTRIÇÕES
# ==========================================

# Acima: Lista de registros capturados
registros_planilha = []

# Acima: Itera sobre cada linha da planilha
for _, linha in df.iterrows():
    # Acima: O relatório traz o RE com dígito verificador (ex: "900632-1") — re_para_int corta no hífen
    re_int = re_para_int(linha["re"])

    # Acima: Se RE inválido, ignora a linha
    if re_int is None:
        continue

    # Acima: Data inicial é obrigatória
    data_inicial = data_ptbr_para_date(linha["data_inicial"])
    if data_inicial is None:
        continue

    # Acima: Monta registro alinhado com a tabela b1.restricoes
    registros_planilha.append({
        "re": re_int,
        "condicao": texto_ou_none(linha["condicao"]),
        "restricao_medica": texto_ou_none(linha["restricao_medica"]),
        "origem": texto_ou_none(linha["origem"]),
        "data_inicial": data_inicial,
        "data_final": data_ptbr_para_date(linha["data_final"]),
        "total_dias": to_int(linha["total_dias"]),
        "observacao": texto_ou_none(linha["observacao"]),
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
# CARGA NO POSTGRES (TRUNCATE + INSERT ALL)
# ==========================================

# Acima: Conecta no Postgres containerizado
conn = conectar_postgres()

# Acima: Cria cursor
cur = conn.cursor()

# Acima: Inicializa métricas
linhas_lidas = len(registros_planilha)
linhas_inseridas = 0

# Acima: ID do ETL para auditoria
etl_id = None

try:
    # Acima: Cria/atualiza registro running em b1.etl_status
    etl_id = iniciar_etl(cur, "restricoes")

    # Acima: Prepara o schema (idempotente): dropa tabelas legadas, cria b1.restricoes se não existir
    preparar_schema(cur)

    # Acima: Comportamento incremental — só adiciona restrições novas, nunca remove ou sobrescreve
    # Acima: Chave natural: (re, origem, data_inicial). observacao no COALESCE trata NULLs sem duplicar.
    # Acima: Contagem antes/depois pra medir quantas foram realmente novas
    cur.execute(f"SELECT count(*) FROM {TABELA_RESTRICOES};")
    total_antes = cur.fetchone()[0]

    # Acima: SQL de insert seletivo — só grava se ainda não existir uma linha com a mesma chave natural
    sql_insert = f"""
        INSERT INTO {TABELA_RESTRICOES}
          (re, condicao, restricao_medica, origem,
           data_inicial, data_final, total_dias, observacao, atualizado_em)
        SELECT %(re)s, %(condicao)s, %(restricao_medica)s, %(origem)s,
               %(data_inicial)s, %(data_final)s, %(total_dias)s, %(observacao)s, now()
        WHERE NOT EXISTS (
            SELECT 1 FROM {TABELA_RESTRICOES}
            WHERE re = %(re)s
              AND origem IS NOT DISTINCT FROM %(origem)s
              AND data_inicial = %(data_inicial)s
        );
    """

    # Acima: Executa em lote (o índice ix_restricoes_natural acelera o EXISTS)
    execute_batch(cur, sql_insert, registros_planilha, page_size=500)

    # Acima: Recomputa total e calcula quantas foram efetivamente inseridas
    cur.execute(f"SELECT count(*) FROM {TABELA_RESTRICOES};")
    total_depois = cur.fetchone()[0]
    linhas_inseridas = total_depois - total_antes
    linhas_ignoradas = len(registros_planilha) - linhas_inseridas

    # Acima: Finaliza ETL e commita (linhas_atualizadas fica 0 — modelo incremental)
    finalizar_etl_sucesso(cur, etl_id, linhas_lidas, linhas_inseridas, 0)
    conn.commit()

    print("\n✅ Atualização concluída.")
    print(f"📥 Linhas lidas: {linhas_lidas}")
    print(f"➕ Novas restrições inseridas: {linhas_inseridas}")
    print(f"↔️  Já existentes (mantidas): {linhas_ignoradas}")
    print(f"📊 Total na tabela agora: {total_depois}")

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
