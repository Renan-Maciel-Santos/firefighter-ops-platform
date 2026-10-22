# ==========================================
# ETL DE TEMPO-RESPOSTA (SDOV2) — 2021 em diante
# ==========================================
# Carrega o export do SDOV2 em b3.tempo_resposta, fechando a lacuna do KPI
# "atendimento de incêndio em até 20 min", que até agora era hardcode/None nos
# relatórios porque não havia fonte de tempo no banco.
#
# Sobre o formato do arquivo: é um export de tabela dinâmica, não uma tabela.
# Duas consequências que ditam quase todo o código abaixo:
#
#   1. Célula repetida vem em branco (mesclada visualmente). A identidade da
#      ocorrência só aparece na PRIMEIRA das suas três linhas, então é preciso
#      arrastar o último valor visto para baixo — o ffill. Sem isso, 2 de cada 3
#      linhas ficam órfãs.
#
#   2. Cada ocorrência ocupa TRÊS linhas, uma por fase do tempo-resposta:
#          01  ligação   -> geração    (atendimento no COBOM)
#          02  geração   -> despacho   (empenho)
#          03  despacho  -> chegada    (deslocamento)
#      O ETL pivota essas três linhas em três colunas.
#
# GRÃO: (ocorrência, viatura). O mesmo id_sdov aparece uma vez por viatura
# empenhada — 123.752 linhas para 112.225 ocorrências. Tratar como se fosse uma
# linha por ocorrência dá média ponderada pelo tamanho do empenho, que não é o
# que ninguém quer medir. Quem precisa do grão de ocorrência usa a view
# b3.vw_tempo_resposta_ocorrencia.
#
# Semântica de carga: merge por (id_sdov, viatura), igual ao de ocorrências —
#   chave nova -> INSERT | chave existente e diferente -> UPDATE | igual -> não toca
#
# Uso:
#     python tempo_resposta_etl.py                      # usa o padrão da pasta
#     python tempo_resposta_etl.py caminho/arquivo.xlsx
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

DOMINIO = "tempo_resposta"

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO_PADRAO = os.path.join(RAIZ, "tempo_resposta", "tempo resposta completo.xlsx")

# Acima: 123 mil linhas num único execute_values consumiria memória à toa
TAMANHO_LOTE = 5000

# Acima: A fase vem no começo do rótulo ("01. tempo resposta médio - ...").
# Casar pelo número e não pelo texto poupa o ETL de quebrar quando alguém
# reescrever a descrição na ferramenta de BI, coisa que o rótulo já sofreu
# (dois dos três terminam num "(2)" que ninguém sabe explicar).
RE_FASE = re.compile(r"^\s*0([123])\s*\.")

# Acima: Prefixo de viatura do 11º GB é <TIPO><11><SGB><NN>. O dígito depois do
# '11' é o subgrupamento. Viatura de outro GB (AB05111, ABS17105) e meio sem
# prefixo padrão (BOTE 01, MEIOSPROPRIOS) não casam e ficam com sgb NULL, que é
# a resposta honesta: apoio mútuo não é desempenho de nenhum SGB nosso.
RE_SGB = re.compile(r"11(\d)\d{2}\s*$")

COLUNAS_DESTINO = [
    "id_sdov", "viatura", "dt_ocorrencia", "num_ocorrencia",
    "municipio", "bairro", "natureza", "sgb",
    "t_atendimento_min", "t_despacho_min", "t_deslocamento_min",
    "lote_importacao",
]


def texto(v):
    v = str(v).strip() if v is not None else ""
    return None if v in ("", "None", "nan", "NaT") else v


def inteiro(v):
    t = texto(v)
    if t is None:
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def numero(v):
    t = texto(v)
    if t is None:
        return None
    try:
        return round(float(t), 4)
    except ValueError:
        return None


def carimbo(v):
    # Acima: A fonte grava dd/mm/aaaa hh:mm:ss, mas o calamine devolve datetime
    # quando a célula é data de verdade — aceita os dois sem adivinhar.
    if isinstance(v, datetime):
        return v
    t = texto(v)
    if t is None:
        return None
    for f in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            continue
    return None


def sgb_da_viatura(vtr):
    if not vtr:
        return None
    m = RE_SGB.search(vtr)
    if not m:
        return None
    # Acima: '0' é sede/EM no padrão de prefixo (UT11002, MT11001), não um SGB.
    return f"{m.group(1)}º SGB" if m.group(1) != "0" else "SEDE"


def ler_ocorrencias(caminho):
    """Lê o export e devolve as linhas já no grão (ocorrência, viatura).

    Faz o ffill da identidade e pivota as três fases. Devolve
    (linhas, total_lido, sem_medicao, sem_identidade).
    """
    wb = CalamineWorkbook.from_path(caminho)
    dados = wb.get_sheet_by_name(wb.sheet_names[0]).to_python()

    # Acima: A linha 0 é a faixa de título da dinâmica ("Data", "viaturas", ...)
    # e a coluna 8 é o único cabeçalho de verdade. Conferir a largura evita
    # carregar lixo caso o export mude de layout.
    if not dados or len(dados[0]) < 9:
        raise SystemExit(f"❌ Layout inesperado: esperava 9 colunas, veio {len(dados[0]) if dados else 0}")

    atual = {}
    grupos = {}
    ordem = []
    lidas = 0
    sem_identidade = 0

    for linha in dados[1:]:
        lidas += 1
        # Acima: ffill — célula em branco herda o último valor visto na coluna
        for idx, campo in enumerate(
            ("data", "num", "id", "vtr", "mun", "bairro", "nat")
        ):
            v = texto(linha[idx])
            if v is not None:
                atual[campo] = v

        fase = RE_FASE.match(str(linha[7] or ""))
        if not fase:
            continue

        if not atual.get("id") or not atual.get("vtr"):
            sem_identidade += 1
            continue

        chave = (inteiro(atual["id"]), atual["vtr"])
        if chave not in grupos:
            grupos[chave] = {
                "dt": carimbo(atual.get("data")),
                "num": inteiro(atual.get("num")),
                "mun": atual.get("mun"),
                "bairro": atual.get("bairro"),
                "nat": atual.get("nat"),
                "fases": {},
            }
            ordem.append(chave)
        grupos[chave]["fases"][fase.group(1)] = numero(linha[8])

    linhas = []
    sem_medicao = 0
    for chave in ordem:
        g = grupos[chave]
        f = g["fases"]
        # Acima: 2.138 ocorrências vêm com as três fases vazias. Entram na tabela
        # mesmo assim: some-las faria o denominador do indicador mentir para mais,
        # sugerindo cobertura de medição que não existe.
        if f.get("1") is None and f.get("2") is None and f.get("3") is None:
            sem_medicao += 1
        linhas.append((
            chave[0], chave[1], g["dt"], g["num"],
            g["mun"], g["bairro"], g["nat"], sgb_da_viatura(chave[1]),
            f.get("1"), f.get("2"), f.get("3"),
            None,  # lote preenchido no main
        ))

    return linhas, lidas, sem_medicao, sem_identidade


def criar_temporaria(cur):
    cur.execute("""
        CREATE TEMP TABLE tmp_tr (LIKE b3.tempo_resposta INCLUDING DEFAULTS)
        ON COMMIT DROP;
    """)
    cur.execute("ALTER TABLE tmp_tr DROP COLUMN IF EXISTS criado_em;")
    cur.execute("ALTER TABLE tmp_tr DROP COLUMN IF EXISTS atualizado_em;")


def gravar_lote(cur, linhas):
    execute_values(
        cur,
        f"INSERT INTO tmp_tr ({', '.join(COLUNAS_DESTINO)}) VALUES %s",
        linhas,
        page_size=1000,
    )


def merge(cur):
    # Acima: O WHERE do DO UPDATE deixa a linha idêntica intocada — é o que torna
    # a recarga barata e mantém atualizado_em honesto.
    chave = ("id_sdov", "viatura")
    atualizaveis = [c for c in COLUNAS_DESTINO if c not in chave]
    sets = ",\n            ".join(f"{c} = EXCLUDED.{c}" for c in atualizaveis)
    comparaveis = [c for c in atualizaveis if c != "lote_importacao"]
    antigos = ", ".join(f"a.{c}" for c in comparaveis)
    novos = ", ".join(f"EXCLUDED.{c}" for c in comparaveis)

    cur.execute(f"""
        INSERT INTO b3.tempo_resposta AS a ({', '.join(COLUNAS_DESTINO)})
        SELECT {', '.join(COLUNAS_DESTINO)} FROM tmp_tr
        ON CONFLICT (id_sdov, viatura) DO UPDATE SET
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

    linhas, lidas, sem_medicao, sem_identidade = ler_ocorrencias(caminho)
    linhas = [l[:-1] + (lote,) for l in linhas]

    print(f"📑 Linhas no arquivo:        {lidas:,}".replace(",", "."))
    print("🔗 Pares ocorrência × viatura: " + f"{len(linhas):,}".replace(",", "."))
    if sem_identidade:
        print(f"⚠️  Sem id/viatura, ignoradas: {sem_identidade:,}".replace(",", "."))
    if sem_medicao:
        pct = 100 * sem_medicao / len(linhas) if linhas else 0
        print(f"⚠️  Sem nenhuma das 3 fases:  {sem_medicao:,} ({pct:.1f}%)".replace(",", "."))

    conn = conectar_postgres()
    cur = conn.cursor()
    etl_id = iniciar_etl(cur, DOMINIO)
    conn.commit()

    try:
        criar_temporaria(cur)
        for i in range(0, len(linhas), TAMANHO_LOTE):
            gravar_lote(cur, linhas[i:i + TAMANHO_LOTE])

        inseridas, atualizadas = merge(cur)
        finalizar_etl_sucesso(cur, etl_id, lidas, inseridas, atualizadas)
        conn.commit()

        print("\n✅ Carga concluída.")
        print(f"➕ Inseridas:      {inseridas:,}".replace(",", "."))
        print(f"🔁 Atualizadas:    {atualizadas:,}".replace(",", "."))
        print(f"⏭️  Sem mudança:    {len(linhas) - inseridas - atualizadas:,}".replace(",", "."))

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
