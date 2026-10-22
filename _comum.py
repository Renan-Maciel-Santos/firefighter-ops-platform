# ==========================================
# MÓDULO COMUM DOS ETLS DE B1
# ==========================================
# Concentra: conexão Postgres, auditoria em b1.etl_status,
# leitura/normalização de células vindas dos relatórios do SGP,
# e localização automática do arquivo em Downloads.
# ==========================================

# Acima: Localização automática do arquivo baixado
import glob

# Acima: Expansão de caminhos (pasta Downloads do usuário)
import os

# Acima: Conversão de datas ptBR (dd/mm/aaaa)
from datetime import datetime

# Acima: Encerramento controlado
import sys

# Acima: Conector PostgreSQL
import psycopg2

# Acima: Leitura das variáveis de ambiente do .env (na raiz do projeto)
from dotenv import load_dotenv

# Acima: Carrega o .env da raiz do projeto (busca a partir da pasta de _comum.py)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


# ==========================================
# CONFIGURAÇÕES POSTGRES (via .env, com fallback pro stack docker)
# ==========================================

# Acima: Host do Postgres (porta publicada 5432:5432 no stack)
PG_HOST = os.environ.get("PG_HOST", "localhost")

# Acima: Porta do Postgres publicada no host
PG_PORT = int(os.environ.get("PG_PORT", "5432"))

# Acima: Nome do banco
PG_DB = os.environ.get("PG_DB", "11gb")

# Acima: Usuário do banco (default inofensivo, não é segredo)
PG_USER = os.environ.get("PG_USER", "admin")
# Acima: A senha NÃO tem valor padrão de propósito. Um fallback no código é um segredo
# no código — e este arquivo é versionado. Ausente a variável, o ETL falha dizendo isso.
PG_PASS = os.environ.get("PG_PASS") or ""
if not PG_PASS:
    print(f"\n❌ Variável obrigatória ausente: PG_PASS\n"
          f"   Defina em {os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')}\n",
          file=sys.stderr)
    sys.exit(1)

# Acima: Tabela de auditoria dos ETLs
TABELA_ETL = "b1.etl_status"

# Acima: Pasta onde o navegador salva os downloads por padrão
PASTA_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


# ==========================================
# CONEXÃO
# ==========================================

def conectar_postgres():
    # Acima: Monta DSN em string
    dsn = (
        f"host={PG_HOST} "
        f"port={PG_PORT} "
        f"dbname={PG_DB} "
        f"user={PG_USER} "
        f"password={PG_PASS}"
    )

    # Acima: Abre conexão forçando UTF-8 no client
    conn = psycopg2.connect(
        dsn=dsn,
        options="-c client_encoding=UTF8"
    )

    # Acima: Desliga autocommit para controlar transação
    conn.autocommit = False

    # Acima: Retorna conexão
    return conn


# ==========================================
# AUDITORIA ETL (b1.etl_status)
# ==========================================

def iniciar_etl(cur, dominio):
    # Acima: UPSERT para garantir 1 linha por domínio e evitar violar UNIQUE(dominio)
    cur.execute(
        f"""
        INSERT INTO {TABELA_ETL}
          (dominio, status, iniciado_em, finalizado_em, linhas_lidas, linhas_inseridas, linhas_atualizadas, erro)
        VALUES
          (%s, 'running', now(), NULL, 0, 0, 0, NULL)
        ON CONFLICT (dominio)
        DO UPDATE SET
          status = 'running',
          iniciado_em = now(),
          finalizado_em = NULL,
          linhas_lidas = 0,
          linhas_inseridas = 0,
          linhas_atualizadas = 0,
          erro = NULL
        RETURNING id;
        """,
        (dominio,)
    )

    # Acima: Captura o id da execução (sempre retorna)
    return cur.fetchone()[0]


def finalizar_etl_sucesso(cur, etl_id, linhas_lidas, linhas_inseridas, linhas_atualizadas):
    # Acima: Finaliza o ETL marcando sucesso e métricas
    cur.execute(
        f"""
        UPDATE {TABELA_ETL}
        SET
          status = 'success',
          finalizado_em = now(),
          linhas_lidas = %s,
          linhas_inseridas = %s,
          linhas_atualizadas = %s,
          erro = NULL
        WHERE id = %s;
        """,
        (linhas_lidas, linhas_inseridas, linhas_atualizadas, etl_id)
    )


def finalizar_etl_erro(cur, etl_id, erro_msg):
    # Acima: Finaliza o ETL marcando erro e salvando mensagem
    cur.execute(
        f"""
        UPDATE {TABELA_ETL}
        SET
          status = 'error',
          finalizado_em = now(),
          erro = %s
        WHERE id = %s;
        """,
        (erro_msg, etl_id)
    )


# ==========================================
# NORMALIZAÇÃO DE CÉLULAS DA PLANILHA
# ==========================================

def texto_ou_none(valor):
    # Acima: Trata None/NaN vindos do pandas
    if valor is None:
        return None

    # Acima: Normaliza para string
    texto = str(valor).strip()

    # Acima: Célula vazia do pandas vira "nan" como string
    if not texto or texto.lower() == "nan":
        return None

    # Acima: Retorna texto limpo
    return texto


def to_int(valor):
    # Acima: Reaproveita a limpeza para tratar None/NaN/vazio
    texto = texto_ou_none(valor)

    # Acima: Sem valor, sem inteiro
    if texto is None:
        return None

    # Acima: Tenta converter (via float para aceitar "365.0" e afins)
    try:
        return int(float(texto))
    except:
        return None


def re_para_int(re_texto):
    # Acima: Reaproveita a limpeza para tratar None/NaN/vazio
    texto = texto_ou_none(re_texto)

    # Acima: Sem valor, sem RE
    if texto is None:
        return None

    # Acima: O relatório traz o RE com dígito verificador após o hífen (ex: "900410-3", "900295-A")
    parte_numerica = texto.split("-")[0].strip()

    # Acima: Converte a parte numérica para int
    return to_int(parte_numerica)


def data_ptbr_para_date(valor):
    # Acima: Reaproveita a limpeza de texto/vazio
    texto = texto_ou_none(valor)

    # Acima: Sem valor, sem data
    if texto is None:
        return None

    # Acima: Relatório traz a data no formato dd/mm/aaaa
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except:
        return None


def normalizar_posto_grad(texto):
    # Acima: Proteção contra None
    if not texto:
        return None

    # Acima: Remove espaços extras
    texto = str(texto).strip()

    # Acima: Se não tiver " PM", retorna como está
    if " PM" not in texto:
        return texto

    # Acima: Divide no primeiro " PM" e reconstrói mantendo até PM
    return texto.split(" PM")[0].strip() + " PM"


# ==========================================
# LOCALIZAÇÃO DO RELATÓRIO
# ==========================================

def localizar_arquivo_relatorio(padrao, caminho_informado=None):
    # Acima: Se o caminho foi passado por argumento, usa direto
    if caminho_informado:
        if not os.path.exists(caminho_informado):
            print(f"❌ Arquivo não encontrado: {caminho_informado}")
            sys.exit(1)
        return caminho_informado

    # Acima: Busca candidatos na pasta Downloads pelo padrão de nome do SGP
    candidatos = glob.glob(os.path.join(PASTA_DOWNLOADS, padrao))

    # Acima: Sem nenhum candidato, não há como continuar
    if not candidatos:
        print(
            f"❌ Nenhum arquivo '{padrao}' encontrado em {PASTA_DOWNLOADS}.\n"
            f"   Exporte o relatório na aba Relatórios do SGP e baixe antes de rodar o script."
        )
        sys.exit(1)

    # Acima: Escolhe o mais recente (última exportação do usuário)
    candidatos.sort(key=os.path.getmtime, reverse=True)
    return candidatos[0]


def confirmar_com_usuario(arquivo_relatorio):
    # Acima: Se o orquestrador setou PULAR_CONFIRMACAO=1, roda sem prompt (útil pra automação)
    if os.environ.get("PULAR_CONFIRMACAO") == "1":
        print(f"📄 Importando (auto): {arquivo_relatorio}")
        return

    # Acima: Pergunta ao usuário se este é o arquivo correto (evita processar planilha errada/antiga)
    resposta = input(
        f"📄 Relatório encontrado: {arquivo_relatorio}\n"
        f"Pressione ENTER para confirmar e importar, ou digite 'n' para cancelar: "
    ).strip().lower()

    # Acima: Cancela se o usuário não confirmar
    if resposta == "n":
        print("❌ Importação cancelada pelo usuário.")
        sys.exit(1)
