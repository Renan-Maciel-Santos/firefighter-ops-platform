# ==========================================
# IMPORTAÇÕES
# ==========================================

# Acima: JSON para serializar o payload RAW
import json

# Acima: SHA256 do conteúdo (dedupe silencioso quando planilha não muda)
import hashlib

# Acima: Classificação dos pedaços da célula de estação (código/nome/telefone)
import re

# Acima: Parse de datas
from datetime import datetime

# Acima: Credencial da service account do Google
from google.oauth2.service_account import Credentials

# Acima: Cliente para ler o Google Sheets
import gspread

# Acima: Insert em lote no Postgres
from psycopg2.extras import execute_values

# Acima: Encerramento controlado e path para importar módulo comum
import sys, os

# Acima: Permite importar _comum da raiz do projeto (compartilhado entre B1, B3 etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Acima: Helpers compartilhados dos ETLs (conexão, auditoria, parsers)
from _env import opcional
from _comum import (
    conectar_postgres,
    iniciar_etl, finalizar_etl_sucesso, finalizar_etl_erro,
    to_int, texto_ou_none, data_ptbr_para_date,
)


# ==========================================
# CONFIGURAÇÕES
# ==========================================

# Acima: Caminho absoluto do JSON da Service Account (leitura da planilha)
CAMINHO_CREDENCIAL = opcional("GOOGLE_SA_JSON", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "credentials", "service-account.json"))

# Acima: ID da planilha do mapa de força
PLANILHA_ID = opcional("MAPA_FORCA_PLANILHA_ID", "ID_DA_PLANILHA_DO_MAPA_DE_FORCA")

# Acima: Nome da aba (None = primeira aba)
NOME_ABA = None

# Acima: Escopos mínimos para leitura
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Acima: A partir de qual linha começar a varrer dados operacionais (linha 6 humana = índice 5)
START_ROW_INDEX = 5

# Acima: Layout dos 4 blocos SGB (nome_do_bloco, coluna_inicial). Cada bloco tem COLS_POR_BLOCO colunas contíguas.
COLS_POR_BLOCO = 8
BLOCOS_SGB = [
    ("1º SGB", 0 * COLS_POR_BLOCO),
    ("2º SGB", 1 * COLS_POR_BLOCO),
    ("3º SGB", 2 * COLS_POR_BLOCO),
    ("4º SGB", 3 * COLS_POR_BLOCO),
]

# Acima: Posição de cada campo dentro do bloco.
# STATUS e EFETIVO são colunas SEPARADAS (a planilha passou a separá-las em 07/2026).
COL_ESTACAO = 0
COL_VIATURA = 1
COL_STATUS = 2
COL_EFETIVO = 3
COL_POSTO = 4
COL_MILITAR = 5
COL_AGUA = 6
COL_MERGULHADORES = 7

# Acima: Prefixos de viatura válidos observados no mapa (guarda o parser contra ruído)
PREFIXOS_VIATURA_VALIDOS = (
    "AB-", "ABS-", "UR-", "VO-", "AT-", "TP-",
    "CM-", "MT-", "AC-", "AE-", "VT-", "SK-",
    "MOB-", "UT-", "BOTE-", "USA-",
)

# Acima: Palavras esperadas em algum lugar da parte superior da planilha (validação de layout)
PALAVRAS_CABECALHO_ESPERADAS = ("ESTAÇÃO", "VIATURA", "EFETIVO")

# Acima: Mínimo de viaturas válidas por captura (abaixo disso, algo mudou na planilha)
MINIMO_ESPERADO = 20

# Acima: Código OPM da estação — 8 a 10 dígitos colados, sem separador
RE_CODIGO_OPM = re.compile(r"^\d{8,10}$")


# ==========================================
# FUNÇÕES AUXILIARES ESPECÍFICAS
# ==========================================

def sha256_text(texto):
    # Acima: Hash SHA256 hex de uma string UTF-8
    h = hashlib.sha256()
    h.update(texto.encode("utf-8"))
    return h.hexdigest()


def parse_data_servico(valor):
    # Acima: A planilha traz a data em dd/mm/aaaa OU dd/mm/aa (ex.: "27/02/26")
    texto = texto_ou_none(valor)
    if texto is None:
        return None

    # Acima: Se tiver hora junto (ex: "06/04/2026 00:00"), pega só a data
    if " " in texto:
        texto = texto.split(" ")[0]

    # Acima: Primeiro tenta o parser padrão do _comum (dd/mm/aaaa)
    data = data_ptbr_para_date(texto)
    if data is not None:
        return data

    # Acima: Fallback para dd/mm/aa (ano curto)
    try:
        return datetime.strptime(texto, "%d/%m/%y").date()
    except ValueError:
        print(f"⚠️ Data inválida no mapa: '{texto}'")
        return None


def parse_situacao_e_efetivo(valor_status, valor_efetivo):
    # Acima: Layout atual — STATUS ("Operando"/"Reserva"/"Baixada") e EFETIVO em colunas separadas
    efetivo = to_int(valor_efetivo)

    # Acima: Layout antigo (até 06/2026) — a coluna de status trazia o número do efetivo quando operando
    numero_no_status = to_int(valor_status)
    if numero_no_status is not None:
        return "OPERANDO", efetivo if efetivo is not None else numero_no_status

    texto = texto_ou_none(valor_status)
    if texto is None:
        return None, efetivo

    return texto.upper(), efetivo


def is_viatura_valida(texto):
    # Acima: Filtra ruído (totais, células deslocadas, células em branco)
    if not texto:
        return False
    return str(texto).strip().upper().startswith(PREFIXOS_VIATURA_VALIDOS)


def validar_cabecalho(dados):
    # Acima: Percorre as primeiras linhas caçando as palavras-chave esperadas
    # Acima: Se pelo menos 2 das 3 aparecem, considera o layout OK
    encontradas = set()

    for idx in range(0, min(START_ROW_INDEX, len(dados))):
        linha_upper = " ".join(str(c or "").upper() for c in dados[idx])
        for palavra in PALAVRAS_CABECALHO_ESPERADAS:
            if palavra in linha_upper:
                encontradas.add(palavra)

    # Acima: Se não achou pelo menos 2 marcadores, o layout mudou — melhor abortar
    if len(encontradas) < 2:
        print(
            f"❌ Cabeçalho inesperado. Marcadores encontrados: {sorted(encontradas) or 'nenhum'}.\n"
            f"   Esperado ao menos 2 de {PALAVRAS_CABECALHO_ESPERADAS} nas primeiras {START_ROW_INDEX} linhas."
        )
        return False

    return True


# ==========================================
# CÉLULAS MESCLADAS
# ==========================================
# A planilha usa merge vertical: a estação, a capacidade de água e o número de
# mergulhadores valem para TODO o grupo de linhas do quartel, não para a viatura
# da primeira linha. O get_all_values() devolve o valor só no topo do range e
# vazio no resto, então sem ler os merges o ETL acaba pendurando a água da
# estação na primeira viatura do grupo (era assim que AC e USA "ganhavam" água).
# ==========================================

def carregar_merges(planilha, aba):
    # Acima: Faixas mescladas da aba, direto dos metadados da planilha
    metadados = planilha.fetch_sheet_metadata()
    for sheet in metadados.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == aba.id:
            return sheet.get("merges", [])
    return []


def indexar_merges_por_coluna(merges):
    # Acima: dict[coluna] -> lista de (linha_inicial, linha_final_exclusiva)
    por_coluna = {}

    for m in merges:
        c0 = m.get("startColumnIndex", 0)
        c1 = m.get("endColumnIndex", 0)
        r0 = m.get("startRowIndex", 0)
        r1 = m.get("endRowIndex", 0)

        for coluna in range(c0, c1):
            por_coluna.setdefault(coluna, []).append((r0, r1))

    return por_coluna


def faixa_mesclada(por_coluna, linha, coluna):
    # Acima: Faixa de linhas que a célula (linha, coluna) cobre. Sem merge, cobre só ela mesma.
    for r0, r1 in por_coluna.get(coluna, ()):
        if r0 <= linha < r1:
            return r0, r1
    return linha, linha + 1


def celula(dados, linha, coluna):
    # Acima: Leitura defensiva da grade (linhas curtas / colunas fora do range)
    if linha >= len(dados):
        return ""
    linha_dados = dados[linha]
    if coluna >= len(linha_dados):
        return ""
    return linha_dados[coluna]


def classificar_pedaco_estacao(texto):
    # Acima: A célula de estação mistura código OPM, nome e telefone do quartel,
    # às vezes na mesma célula separados por quebra de linha.
    t = texto.strip()
    if not t:
        return None, None

    # Acima: Tem letra → é (parte do) nome da estação
    if any(ch.isalpha() for ch in t):
        return "nome", t

    # Acima: Só dígitos colados → código OPM
    if RE_CODIGO_OPM.match(t):
        return "codigo", t

    # Acima: Dígitos com separador (0000-1301, 0000 8845) → telefone do quartel
    if len(re.sub(r"\D", "", t)) >= 8:
        return "telefone", t

    return None, None


def extrair_estacao(dados, base_col, linha_inicial, linha_final):
    # Acima: Varre a coluna de estação dentro do grupo e separa código / nome / telefone
    nomes, codigo, telefone = [], None, None

    for linha in range(linha_inicial, linha_final):
        bruto = str(celula(dados, linha, base_col + COL_ESTACAO)).replace("\r", "")
        for pedaco in bruto.split("\n"):
            pedaco = pedaco.strip()
            if not pedaco:
                continue

            # Acima: Código OPM colado no começo do nome ("990112103    BC SÃO LUIZ DO PARAITINGA")
            m_codigo = re.match(r"^(\d{8,10})\s+(.*)$", pedaco)
            if m_codigo:
                if codigo is None:
                    codigo = m_codigo.group(1)
                pedaco = m_codigo.group(2).strip()

            # Acima: Telefone colado no fim do nome ("PB ANA EMILIA 0000-2201")
            m_tel = re.search(r"\s+(\d{4,5}[-\s]?\d{4})$", pedaco)
            if m_tel and any(ch.isalpha() for ch in pedaco):
                if telefone is None:
                    telefone = m_tel.group(1)
                pedaco = pedaco[:m_tel.start()].strip()

            tipo, valor = classificar_pedaco_estacao(pedaco)
            if tipo == "nome":
                # Acima: O nome costuma repetir entre as sub-células mescladas da estação
                if valor.upper() not in {n.upper() for n in nomes}:
                    nomes.append(valor)
            elif tipo == "codigo" and codigo is None:
                codigo = valor
            elif tipo == "telefone" and telefone is None:
                telefone = valor

    # Acima: Nomes quebrados em duas linhas ("EB CAMPOS" + "DO JORDÃO") viram um só
    nome = re.sub(r"\s+", " ", " ".join(nomes)).strip() or None

    return {"estacao_nome": nome, "estacao_codigo": codigo, "estacao_telefone": telefone}


def parse_estacoes(dados, por_coluna):
    # Acima: Uma entrada por estação, com as viaturas daquele quartel dentro
    estacoes = []

    for bloco_nome, base_col in BLOCOS_SGB:
        col_agua = base_col + COL_AGUA
        linha = START_ROW_INDEX

        while linha < len(dados):
            # Acima: O grupo da estação é a faixa mesclada da coluna de água
            r0, r1 = faixa_mesclada(por_coluna, linha, col_agua)
            r0 = max(r0, START_ROW_INDEX)
            r1 = min(r1, len(dados))

            viaturas = []
            for r in range(r0, r1):
                viatura = celula(dados, r, base_col + COL_VIATURA)
                if not is_viatura_valida(viatura):
                    continue

                situacao, efetivo_qtd = parse_situacao_e_efetivo(
                    celula(dados, r, base_col + COL_STATUS),
                    celula(dados, r, base_col + COL_EFETIVO),
                )

                posto = celula(dados, r, base_col + COL_POSTO)
                militar = celula(dados, r, base_col + COL_MILITAR)

                viaturas.append({
                    "ordem": r + 1,
                    "viatura": str(viatura).strip().upper(),
                    "situacao": situacao,
                    "efetivo_qtd": efetivo_qtd,
                    "posto_graduacao": texto_ou_none(posto) and str(posto).strip().upper(),
                    "militar_e_telefone": texto_ou_none(militar) and str(militar).strip().upper(),
                })

            # Acima: Grupo sem nenhuma viatura é rodapé/linha em branco — não vira estação
            if viaturas:
                estacao = extrair_estacao(dados, base_col, r0, r1)
                estacao.update({
                    "bloco_nome": bloco_nome,
                    "ordem": r0 + 1,
                    # Acima: Água e mergulhadores ficam no topo do range mesclado
                    "capacidade_agua_l": to_int(celula(dados, r0, col_agua)),
                    "mergulhadores": to_int(celula(dados, r0, base_col + COL_MERGULHADORES)),
                    "viaturas": viaturas,
                })
                estacoes.append(estacao)

            linha = r1

    return estacoes


# ==========================================
# LEITURA DA PLANILHA (GOOGLE SHEETS)
# ==========================================

# Acima: Autentica no Google via service account
credenciais = Credentials.from_service_account_file(CAMINHO_CREDENCIAL, scopes=SCOPES)
cliente = gspread.authorize(credenciais)
planilha = cliente.open_by_key(PLANILHA_ID)

# Acima: Seleciona a aba (por nome ou primeira aba)
aba = planilha.worksheet(NOME_ABA) if NOME_ABA else planilha.sheet1

# Acima: Lê a grade inteira de uma vez (1 chamada à API)
dados = aba.get_all_values()

# Acima: Valida cabeçalho antes de qualquer processamento (aborta cedo se layout mudou)
if not validar_cabecalho(dados):
    sys.exit(1)

# Acima: Faixas mescladas (1 chamada à API) — sem elas a água cai na viatura errada
por_coluna = indexar_merges_por_coluna(carregar_merges(planilha, aba))

# Acima: Extrai data do serviço (linha 1) e cabecalho_texto (linha 2)
data_servico = parse_data_servico(dados[0][0]) if dados and dados[0] else None
cabecalho_texto = dados[1][0].strip() if len(dados) > 1 and dados[1] and dados[1][0] else None

# Acima: Sem data o snapshot fica sem âncora temporal — não é fatal, mas precisa aparecer no log
if data_servico is None:
    print("⚠️ ATENÇÃO: a célula A1 da planilha veio sem data de serviço. "
          "O snapshot será gravado com data_servico nulo.")

# Acima: Serializa payload como JSON estável (para hash consistente)
payload_json = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
conteudo_sha = sha256_text(payload_json)

# Acima: Agrupa por estação e parseia as viaturas de cada uma
estacoes = parse_estacoes(dados, por_coluna)
total_viaturas = sum(len(e["viaturas"]) for e in estacoes)

# Acima: Proteção contra layout quebrado (ex.: alguém reorganizou colunas e o parser produziu poucas linhas)
if total_viaturas < MINIMO_ESPERADO:
    print(
        f"❌ Captura suspeita (apenas {total_viaturas} viaturas). "
        f"Abaixo do mínimo {MINIMO_ESPERADO}. Abortando para não gravar snapshot ruim."
    )
    sys.exit(1)

agua_total = sum(e["capacidade_agua_l"] or 0 for e in estacoes)
merg_total = sum(e["mergulhadores"] or 0 for e in estacoes)
efetivo_total = sum(v["efetivo_qtd"] or 0 for e in estacoes for v in e["viaturas"])

print(f"🔎 Data serviço: {data_servico} | linhas na grade: {len(dados)}")
print(f"🔎 Estações: {len(estacoes)} | viaturas: {total_viaturas} | efetivo: {efetivo_total} "
      f"| água: {agua_total} L | mergulhadores: {merg_total}")


# ==========================================
# GRAVAÇÃO NO POSTGRES
# ==========================================

# Acima: Conecta usando o helper compartilhado
conn = conectar_postgres()
cur = conn.cursor()

# Acima: Inicializa métricas para auditoria
linhas_lidas = total_viaturas
linhas_inseridas = 0
linhas_atualizadas = 0
etl_id = None

try:
    # Acima: Registra início do ETL em b1.etl_status (mesmo padrão dos scripts B1)
    etl_id = iniciar_etl(cur, "mapa_forca")

    # Acima: Insere snapshot RAW (ou ignora se conteúdo idêntico já foi capturado)
    cur.execute(
        """
        INSERT INTO b3.mapa_forca_snapshot_raw
          (fonte_planilha_id, fonte_aba, data_servico, cabecalho_texto, conteudo_sha256, payload_raw)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (fonte_planilha_id, fonte_aba, conteudo_sha256) DO NOTHING
        RETURNING id;
        """,
        (PLANILHA_ID, aba.title, data_servico, cabecalho_texto, conteudo_sha, payload_json),
    )

    row = cur.fetchone()
    snapshot_id = row[0] if row else None
    snapshot_novo = snapshot_id is not None

    # Acima: Se snapshot já existia (conteúdo idêntico), localiza o id existente
    if snapshot_id is None:
        cur.execute(
            """
            SELECT id FROM b3.mapa_forca_snapshot_raw
            WHERE fonte_planilha_id = %s AND fonte_aba = %s AND conteudo_sha256 = %s
            LIMIT 1;
            """,
            (PLANILHA_ID, aba.title, conteudo_sha),
        )
        snapshot_id = cur.fetchone()[0]

    # Acima: Reescreve estações e linhas do snapshot (DELETE + INSERT idempotente)
    cur.execute("DELETE FROM b3.mapa_forca_linha   WHERE snapshot_id = %s;", (snapshot_id,))
    cur.execute("DELETE FROM b3.mapa_forca_estacao WHERE snapshot_id = %s;", (snapshot_id,))

    valores_linha = []

    for est in estacoes:
        # Acima: Grava a estação primeiro para pendurar as viaturas nela
        cur.execute(
            """
            INSERT INTO b3.mapa_forca_estacao
              (snapshot_id, bloco_nome, estacao_nome, estacao_codigo, estacao_telefone,
               capacidade_agua_l, mergulhadores, ordem)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                snapshot_id, est["bloco_nome"], est["estacao_nome"],
                est["estacao_codigo"], est["estacao_telefone"],
                est["capacidade_agua_l"], est["mergulhadores"], est["ordem"],
            ),
        )
        estacao_id = cur.fetchone()[0]

        for v in est["viaturas"]:
            valores_linha.append((
                snapshot_id, estacao_id,
                est["bloco_nome"], est["estacao_nome"], v["viatura"],
                v["situacao"], v["efetivo_qtd"],
                v["posto_graduacao"], v["militar_e_telefone"], v["ordem"],
            ))

    # Acima: capacidade_agua_l e mergulhadores NÃO entram aqui de propósito —
    # são da estação, não da viatura, e ficam em b3.mapa_forca_estacao.
    if valores_linha:
        execute_values(
            cur,
            """
            INSERT INTO b3.mapa_forca_linha
              (snapshot_id, estacao_id, bloco_nome, estacao_bombeiros, viatura,
               situacao, efetivo_qtd, posto_graduacao, militar_e_telefone, ordem)
            VALUES %s;
            """,
            valores_linha,
            page_size=500,
        )

    # Acima: Métrica — snapshot novo = inserção, snapshot já existia = atualização (mesmo id, linhas reescritas)
    if snapshot_novo:
        linhas_inseridas = len(valores_linha)
    else:
        linhas_atualizadas = len(valores_linha)

    finalizar_etl_sucesso(cur, etl_id, linhas_lidas, linhas_inseridas, linhas_atualizadas)
    conn.commit()

    print(f"✅ Snapshot: id={snapshot_id} | {'NOVO' if snapshot_novo else 'reprocessado (conteúdo igual)'}")
    print(f"✅ Estações gravadas: {len(estacoes)} | viaturas gravadas: {len(valores_linha)}")

except Exception as e:
    conn.rollback()

    # Acima: Tenta registrar o erro no ETL em uma transação nova
    try:
        if etl_id is not None:
            cur2 = conn.cursor()
            finalizar_etl_erro(cur2, etl_id, str(e))
            conn.commit()
            cur2.close()
    except:
        pass

    print("\n❌ Falha na captura do mapa de força. ROLLBACK executado.")
    print("Erro:", e)
    sys.exit(1)

finally:
    try:
        cur.close()
    except:
        pass
    try:
        conn.close()
    except:
        pass
