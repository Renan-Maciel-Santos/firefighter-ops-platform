"""
Importa o QPO (Vol. XIX) no nível de SEÇÃO e FUNÇÃO -> b1.qpo_funcoes

Uso: python importar_qpo_funcoes.py [caminho_do_xls]

POR QUE ESTA TABELA EXISTE
b1.qpo_vagas guarda o QPO agregado por lotação, quadro e posto: 5 lotações,
23 linhas, 588 vagas. Com ela o painel responde "o EM tem 1 claro" — e para
por aí. A estrutura interna do EM não está lá, e é ela que muda decisão: em
09/09/2026 o EM aparecia com 1 claro no agregado, enquanto a Seção de
Atividades Técnicas estava com 8 vagas vazias de 21 e o B/1-B/5 com 5 acima
do quadro. Um número escondia os dois.

Esta tabela guarda o mesmo QPO no nível em que o documento foi escrito:
Comandante, Chefe do B/4, Auxiliares do COBOM, Estação de Bombeiros de
Ubatuba. b1.qpo_vagas NÃO é tocada — o painel depende dela.

RELAÇÃO ENTRE AS DUAS
A soma daqui tem de bater com a de lá, lotação por lotação. O script confere
isso ao final e ABORTA sem gravar se divergir: um QPO granular que não fecha
com o agregado é pior que nenhum, porque as duas respostas ficam plausíveis.

POSIÇÕES ENTRE PARÊNTESES
No documento, `(1)` é posto previsto SEM vaga própria — "a ser designado pelo
Comandante". A Agência de Área do EM é inteira assim: 2 posições, 0 vagas, e
2 militares nela hoje. Guardamos o número em `vagas` com `a_designar = true`,
para não perder a informação; quem soma vagas de verdade filtra
`WHERE NOT a_designar`, que é o que o próprio documento faz nas linhas SOMA.

NÃO É ETL RECORRENTE
O QPO muda por ato administrativo, não por captura diária. Por isso não se
registra em b1.etl_status e não entra na vigilância de frescor do
bia_watchdog.py — cobrar cadência de quem não tem cadência só produz alarme.
Rode à mão quando sair volume novo.
"""

import os
import sys

import psycopg2
import xlrd
from psycopg2.extras import execute_batch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir, opcional

PG_HOST = opcional("PG_HOST", "localhost")
PG_PORT = int(opcional("PG_PORT", "5432"))
PG_DB   = opcional("PG_DB", "11gb")
PG_USER = opcional("PG_USER", "admin")
PG_PASS = exigir("PG_PASS")

PADRAO = os.path.join(os.path.dirname(__file__), "QPO_11GB.xls")
ARQUIVO = sys.argv[1] if len(sys.argv) > 1 else PADRAO
FONTE = "QPO Vol. XIX"

# Grafia da lotação igual à de b1.qpo_vagas, senão o join entre as duas não
# fecha e o claro por seção fica órfão.
LOTACAO_DA_ABA = {
    "11GB": "EM",
    "1SGB": "1°Sgb",
    "2SGB": "2°Sgb",
    "3SGB": "3°Sgb",
    "4SGB": "4°Sgb",
}

# A aba 11GB tem uma coluna de ESTRUTURA a mais que as dos SGB; todo o resto
# do layout é o mesmo, deslocado de 1.
DESLOC = {"11GB": 0, "1SGB": 1, "2SGB": 1, "3SGB": 1, "4SGB": 1}

# Índices na aba 11GB. Para as abas de SGB, subtraia DESLOC.
COL_ESTRUTURA = (2, 3, 4, 5)
COL_FUNCAO    = 6
COL_OFICIAL   = {7: "Cel PM", 8: "Ten Cel PM", 9: "Maj PM", 10: "Cap PM", 11: "Ten PM"}
COL_OUTROS    = {12: "Cel PM", 13: "Ten Cel PM", 14: "Maj PM", 15: "Cap PM", 16: "Ten PM"}
COL_QUADRO    = 17
COL_QOS       = 18
COL_PRACA     = {20: "Subten/Sgt", 21: "Cb/Sd"}
COL_OBS       = 24
COL_MUNICIPIO = 24   # só nas abas de SGB, onde OBS cai em 23


def texto(sh, i, j):
    if j < 0 or j >= sh.ncols:
        return ""
    v = sh.cell_value(i, j)
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v).replace("\n", " ").strip()


def numero(bruto):
    """Devolve (vagas, a_designar). '' -> None. '(1)' -> (1, True). '3' -> (3, False)."""
    if not bruto:
        return None, False
    designar = bruto.startswith("(") and bruto.endswith(")")
    limpo = bruto.strip("()").strip()
    try:
        n = int(float(limpo))
    except ValueError:
        return None, False
    if n == 0 and not designar:
        return None, False
    return n, designar


def ler_aba(wb, aba):
    sh = wb.sheet_by_name(aba)
    lotacao = LOTACAO_DA_ABA[aba]
    d = DESLOC[aba]

    estrutura = ["", "", "", ""]
    linhas = []

    for i in range(6, sh.nrows):
        primeira = texto(sh, i, 0)
        if primeira.replace(" ", "").upper().startswith("TOTAL"):
            break
        if primeira.upper().startswith("OBSERVA"):
            break

        # Atualiza a hierarquia. Mexer num nível zera os mais fundos, senão a
        # subseção anterior vaza para a seção seguinte.
        for nivel, col in enumerate(COL_ESTRUTURA):
            v = texto(sh, i, col - d)
            if v:
                estrutura[nivel] = v
                for mais_fundo in range(nivel + 1, len(estrutura)):
                    estrutura[mais_fundo] = ""

        # Na aba 11GB, as linhas dos SGB são só o resumo do que já vem
        # detalhado nas abas próprias. Detalhe vence resumo.
        if aba == "11GB" and estrutura[1].upper().endswith("SGB"):
            continue

        funcao = texto(sh, i, COL_FUNCAO - d)
        niveis = [n for n in estrutura if n and n != "EM"]
        secao = niveis[0] if niveis else "Comando"
        subsecao = " / ".join(niveis[1:]) or None

        obs = texto(sh, i, (COL_OBS if aba == "11GB" else 23))
        municipio = texto(sh, i, COL_MUNICIPIO) if aba != "11GB" else ""

        def guardar(coluna, posto, quadro, categoria):
            vagas, designar = numero(texto(sh, i, coluna - d))
            if vagas is None:
                return
            linhas.append({
                "lotacao": lotacao, "secao": secao, "subsecao": subsecao,
                "funcao": funcao or None, "quadro": quadro, "posto_grad": posto,
                "categoria": categoria, "vagas": vagas, "a_designar": designar,
                "municipio": municipio or None, "obs": obs or None,
                "aba_origem": aba, "linha_origem": i + 1, "fonte": FONTE,
            })

        for col, posto in COL_OFICIAL.items():
            guardar(col, posto, "QOPM", "Oficial")

        # O quadro dos oficiais de OUTROS vem escrito numa coluna à parte
        # (QAOPM, no 11º GB). Sem ela não dá para saber de que quadro é a vaga.
        quadro_outros = texto(sh, i, COL_QUADRO - d) or "QAOPM"
        for col, posto in COL_OUTROS.items():
            guardar(col, posto, quadro_outros, "Oficial")

        guardar(COL_QOS, "Oficial QOS", "QOS", "Oficial")

        for col, posto in COL_PRACA.items():
            guardar(col, posto, "QPPM", "Praça")

    return linhas


DDL = """
CREATE TABLE IF NOT EXISTS b1.qpo_funcoes (
    id           SERIAL PRIMARY KEY,
    lotacao      TEXT    NOT NULL,
    secao        TEXT,
    subsecao     TEXT,
    funcao       TEXT,
    quadro       TEXT    NOT NULL,
    posto_grad   TEXT    NOT NULL,
    categoria    TEXT    NOT NULL,
    vagas        INTEGER NOT NULL,
    a_designar   BOOLEAN NOT NULL DEFAULT false,
    municipio    TEXT,
    obs          TEXT,
    aba_origem   TEXT    NOT NULL,
    linha_origem INTEGER NOT NULL,
    fonte        TEXT    NOT NULL,
    criado_em    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_qpo_func_lotacao  ON b1.qpo_funcoes (lotacao);
CREATE INDEX IF NOT EXISTS ix_qpo_func_secao    ON b1.qpo_funcoes (secao);
CREATE INDEX IF NOT EXISTS ix_qpo_func_categoria ON b1.qpo_funcoes (categoria);
"""

INSERT = """
INSERT INTO b1.qpo_funcoes
    (lotacao, secao, subsecao, funcao, quadro, posto_grad, categoria,
     vagas, a_designar, municipio, obs, aba_origem, linha_origem, fonte)
VALUES
    (%(lotacao)s, %(secao)s, %(subsecao)s, %(funcao)s, %(quadro)s,
     %(posto_grad)s, %(categoria)s, %(vagas)s, %(a_designar)s,
     %(municipio)s, %(obs)s, %(aba_origem)s, %(linha_origem)s, %(fonte)s)
"""


def main():
    if not os.path.exists(ARQUIVO):
        print(f"[ERRO] arquivo nao encontrado: {ARQUIVO}", file=sys.stderr)
        raise SystemExit(1)

    print(f"[*] Lendo {ARQUIVO}")
    wb = xlrd.open_workbook(ARQUIVO)

    linhas = []
    for aba in LOTACAO_DA_ABA:
        if aba not in wb.sheet_names():
            print(f"[ERRO] aba '{aba}' ausente na planilha", file=sys.stderr)
            raise SystemExit(1)
        lidas = ler_aba(wb, aba)
        soma = sum(l["vagas"] for l in lidas if not l["a_designar"])
        print(f"    {aba:5} -> {len(lidas):3} linhas, {soma:3} vagas")
        linhas += lidas

    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB,
                            user=PG_USER, password=PG_PASS)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(DDL)

            # Confere ANTES de gravar: se o granular não fecha com o agregado,
            # o certo é não existir. Duas respostas plausíveis e diferentes
            # para "quantas vagas tem o EM" é o pior resultado possível.
            cur.execute("SELECT lotacao, SUM(vagas) FROM b1.qpo_vagas GROUP BY 1")
            oficial = {l: int(v) for l, v in cur.fetchall()}

            meu = {}
            for l in linhas:
                if not l["a_designar"]:
                    meu[l["lotacao"]] = meu.get(l["lotacao"], 0) + l["vagas"]

            divergencias = []
            for lot in sorted(set(oficial) | set(meu)):
                a, b = oficial.get(lot, 0), meu.get(lot, 0)
                marca = "ok" if a == b else "DIVERGE"
                print(f"    {lot:8} qpo_vagas={a:4}  qpo_funcoes={b:4}  {marca}")
                if a != b:
                    divergencias.append((lot, a, b))

            if divergencias:
                print("\n[ERRO] o granular nao fecha com b1.qpo_vagas. "
                      "Nada foi gravado.", file=sys.stderr)
                for lot, a, b in divergencias:
                    print(f"        {lot}: agregado {a} x granular {b}", file=sys.stderr)
                raise SystemExit(2)

            # REPLACE: o QPO é um retrato inteiro, não um incremento.
            cur.execute("DELETE FROM b1.qpo_funcoes WHERE fonte = %s", (FONTE,))
            execute_batch(cur, INSERT, linhas, page_size=200)

        print(f"\n[OK] {len(linhas)} linhas gravadas em b1.qpo_funcoes "
              f"({sum(l['vagas'] for l in linhas if not l['a_designar'])} vagas).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
