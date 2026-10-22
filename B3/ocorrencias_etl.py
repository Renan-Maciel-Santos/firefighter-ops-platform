# ==========================================
# ETL DE OCORRÊNCIAS (COBOM) — 2021 em diante
# ==========================================
# Carrega o export do COBOM em b3.ocorrencias. Fecha a lacuna apontada no
# escopo: o router /ocorrencias do webapp devolvia zeros escritos no código.
#
# Sobre o arquivo de origem: é .xls legado (OLE2/BIFF8) de ~350 MB, paginado
# em 6 abas por causa do limite de 65.536 linhas do formato. Só a primeira aba
# tem cabeçalho. Lido com engine calamine — xlrd é ordens de magnitude mais
# lento num arquivo deste porte.
#
# Filtro: só STATUSID = 5 (ocorrência finalizada). As 251.696 linhas com
# STATUSID = 0 são casca — sem natureza, endereço, comandante ou finalização.
#
# Semântica de carga (merge, igual ao de afastamentos):
#   chave nova -> INSERT | chave existente e diferente -> UPDATE | igual -> não toca
#
# Uso:
#     python ocorrencias_etl.py                        # usa o padrão em Downloads
#     python ocorrencias_etl.py caminho/arquivo.xls
# ==========================================

import os
import re
import sys
from datetime import datetime

from psycopg2.extras import execute_values
from python_calamine import CalamineWorkbook

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _comum import (
    conectar_postgres,
    iniciar_etl,
    finalizar_etl_sucesso,
    finalizar_etl_erro,
)

DOMINIO = "ocorrencias"

ARQUIVO_PADRAO = os.path.join(os.path.expanduser("~"), "Downloads", "Untitled.xls")

# Acima: Só as linhas finalizadas entram
STATUS_ACEITO = 5

# Acima: Lote a cada N linhas — 131 mil registros num único execute_values
# consumiria memória sem necessidade
TAMANHO_LOTE = 5000

# Acima: "POINT (-44.9761 -22.5813) | 4674" -> (lon, lat). A ordem é lon lat,
# como manda o WKT — trocar produziria coordenadas no meio do oceano.
RE_PONTO = re.compile(r"POINT\s*\(\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s*\)", re.I)


def texto(v):
    v = str(v).strip() if v is not None else ""
    return None if v in ("", "None", "nan") else v


def inteiro(v):
    t = texto(v)
    if t is None:
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def carimbo(v):
    t = texto(v)
    if t is None:
        return None
    for f in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            continue
    return None


def data(v):
    c = carimbo(v)
    return c.date() if c else None


def ponto(v):
    t = texto(v)
    if not t:
        return None, None
    m = RE_PONTO.search(t)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


COLUNAS_DESTINO = [
    "id", "ocrnum", "ocrdat", "statusid", "cadcod", "situacaoid", "atendimentotipoid",
    "natcod", "dt_chamada", "dt_geracao", "dt_finalizacao", "dt_homologacao",
    "despacho_min", "sgb", "gb", "comando", "pb", "opm_fato", "opm_atendimento",
    "logradouro_inicial", "numero_inicial", "complemento_inicial", "bairro_inicial",
    "referencia_inicial", "municipio_inicial", "endereco_inicial",
    "logradouro_final", "numero_final", "complemento_final", "bairro_final",
    "municipio_final", "cep_final", "endereco",
    "localizacao_inicial", "localizacao_final",
    "lon_inicial", "lat_inicial", "lon_final", "lat_final",
    "dados_complementares", "historico", "motivo_devolucao",
    "comandante_cpf", "homologador_cpf", "possui_guia", "ocr_rst_cod", "lote_importacao",
]


def montar_linha(l, I, lote):
    chamada = carimbo(l[I["OcrChmDat"]])
    geracao = carimbo(l[I["OCRGREDAT"]])

    # Acima: Gravado na carga porque a conta é sempre a mesma. Sem sanear aqui:
    # a fonte tem negativos e valores absurdos, e mascarar isso na carga
    # esconderia um problema de qualidade que quem consulta precisa ver.
    despacho = None
    if chamada and geracao:
        despacho = round((geracao - chamada).total_seconds() / 60, 2)

    lon_i, lat_i = ponto(l[I["LOCALIZACAOINICIAL"]])
    lon_f, lat_f = ponto(l[I["LOCALIZACAOFINAL"]])

    return (
        inteiro(l[I["ID"]]), inteiro(l[I["OCRNUM"]]), data(l[I["OCRDAT"]]),
        inteiro(l[I["STATUSID"]]), inteiro(l[I["CADCOD"]]), inteiro(l[I["SITUACAOID"]]),
        inteiro(l[I["ATENDIMENTOTIPOID"]]), texto(l[I["NATCOD"]]),
        chamada, geracao, carimbo(l[I["DATAFINALIZACAO"]]), carimbo(l[I["DATAHOMOLOGACAO"]]),
        despacho,
        texto(l[I["SGB"]]), texto(l[I["GB"]]), texto(l[I["COMANDO"]]), texto(l[I["PB"]]),
        inteiro(l[I["OPMFATO"]]), inteiro(l[I["OPMATENDIMENTO"]]),
        texto(l[I["LOGRADOUROINICIAL"]]), texto(l[I["NUMEROINICIAL"]]),
        texto(l[I["COMPLEMENTOINICIAL"]]), texto(l[I["BAIRROINICIAL"]]),
        texto(l[I["REFERENCIAINICIAL"]]), inteiro(l[I["MUNICIPIOIDINICIAL"]]),
        texto(l[I["ENDERECOINICIAL"]]),
        texto(l[I["LOGRADOUROFINAL"]]), texto(l[I["NUMEROFINAL"]]),
        texto(l[I["COMPLEMENTOFINAL"]]), texto(l[I["BAIRROFINAL"]]),
        inteiro(l[I["MUNICIPIOIDFINAL"]]), texto(l[I["CEPFINAL"]]), texto(l[I["ENDERECO"]]),
        texto(l[I["LOCALIZACAOINICIAL"]]), texto(l[I["LOCALIZACAOFINAL"]]),
        lon_i, lat_i, lon_f, lat_f,
        texto(l[I["DADOSCOMPLEMENTARES"]]), texto(l[I["HISTORICO"]]),
        texto(l[I["MOTIVODEVOLUCAO"]]),
        texto(l[I["COMANDANTECPF"]]), texto(l[I["HOMOLOGADORCPF"]]),
        inteiro(l[I["POSSUIAGUIA"]]), inteiro(l[I["OcrRstCod"]]), lote,
    )


def criar_temporaria(cur):
    cur.execute(f"""
        CREATE TEMP TABLE tmp_ocr (LIKE b3.ocorrencias INCLUDING DEFAULTS)
        ON COMMIT DROP;
    """)
    cur.execute("ALTER TABLE tmp_ocr DROP COLUMN IF EXISTS criado_em;")
    cur.execute("ALTER TABLE tmp_ocr DROP COLUMN IF EXISTS atualizado_em;")


def gravar_lote(cur, linhas):
    execute_values(
        cur,
        f"INSERT INTO tmp_ocr ({', '.join(COLUNAS_DESTINO)}) VALUES %s",
        linhas,
        page_size=1000,
    )


def merge(cur):
    # Acima: O WHERE do DO UPDATE faz a linha idêntica não ser tocada — é o que
    # torna a recarga barata e mantém atualizado_em honesto.
    atualizaveis = [c for c in COLUNAS_DESTINO if c != "id"]
    sets = ",\n            ".join(f"{c} = EXCLUDED.{c}" for c in atualizaveis)
    antigos = ", ".join(f"a.{c}" for c in atualizaveis if c != "lote_importacao")
    novos = ", ".join(f"EXCLUDED.{c}" for c in atualizaveis if c != "lote_importacao")

    cur.execute(f"""
        INSERT INTO b3.ocorrencias AS a ({', '.join(COLUNAS_DESTINO)})
        SELECT {', '.join(COLUNAS_DESTINO)} FROM tmp_ocr
        ON CONFLICT (id) DO UPDATE SET
            {sets},
            atualizado_em = now()
        WHERE ({antigos}) IS DISTINCT FROM ({novos})
        RETURNING (xmax = 0) AS inserida;
    """)
    r = cur.fetchall()
    inseridas = sum(1 for (i,) in r if i)
    return inseridas, len(r) - inseridas


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else ARQUIVO_PADRAO
    if not os.path.exists(caminho):
        print(f"❌ Arquivo não encontrado: {caminho}")
        sys.exit(1)

    lote = f"{os.path.basename(caminho)}__{datetime.now():%Y-%m-%d_%H-%M-%S}"
    print(f"📂 Lendo {caminho} ({os.path.getsize(caminho)/1048576:.0f} MB)")

    wb = CalamineWorkbook.from_path(caminho)
    print(f"📑 Abas: {len(wb.sheet_names)}")

    cabecalho = [str(c).strip() for c in wb.get_sheet_by_name(wb.sheet_names[0]).to_python()[0]]
    I = {c: i for i, c in enumerate(cabecalho)}

    faltando = [c for c in ("ID", "OCRDAT", "STATUSID", "OcrChmDat", "OCRGREDAT", "NATCOD", "SGB")
                if c not in I]
    if faltando:
        print(f"❌ Layout inesperado — colunas ausentes: {faltando}")
        sys.exit(1)

    conn = conectar_postgres()
    cur = conn.cursor()
    etl_id = iniciar_etl(cur, DOMINIO)
    conn.commit()

    try:
        criar_temporaria(cur)

        lidas = aceitas = 0
        buffer = []
        vistos = set()

        for nome in wb.sheet_names:
            dados = wb.get_sheet_by_name(nome).to_python()
            inicio = 1 if nome == wb.sheet_names[0] else 0
            for l in dados[inicio:]:
                lidas += 1
                if inteiro(l[I["STATUSID"]]) != STATUS_ACEITO:
                    continue
                oid = inteiro(l[I["ID"]])
                if oid is None or oid in vistos:
                    continue
                vistos.add(oid)
                buffer.append(montar_linha(l, I, lote))
                aceitas += 1
                if len(buffer) >= TAMANHO_LOTE:
                    gravar_lote(cur, buffer)
                    buffer = []
            print(f"   {nome}: acumulado {aceitas:,} aceitas de {lidas:,} lidas")

        if buffer:
            gravar_lote(cur, buffer)

        inseridas, atualizadas = merge(cur)
        finalizar_etl_sucesso(cur, etl_id, lidas, inseridas, atualizadas)
        conn.commit()

        print(f"\n✅ Carga concluída.")
        print(f"📥 Linhas no arquivo:   {lidas:,}")
        print(f"✅ Aceitas (STATUS={STATUS_ACEITO}): {aceitas:,}")
        print(f"➕ Inseridas:           {inseridas:,}")
        print(f"🔁 Atualizadas:         {atualizadas:,}")
        print(f"⏭️  Sem mudança:         {aceitas - inseridas - atualizadas:,}")

    except Exception as e:
        conn.rollback()
        try:
            finalizar_etl_erro(cur, etl_id, str(e))
            conn.commit()
        except Exception:
            conn.rollback()
        print(f"❌ Falhou: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
