"""
ETL do SJD — carrega o xlsx do SJD nas tabelas sjd.processos e sjd.indicadores_mensais.

Uso:
    python sjd_etl.py                       # padrão: dados_externos/sjd_<ano-corrente>-S1.xlsx e ...S2.xlsx
    python sjd_etl.py <caminho.xlsx>        # carrega um arquivo específico
"""

import os, sys, hashlib, glob
from datetime import date
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _comum import (
    conectar_postgres, iniciar_etl,
    finalizar_etl_sucesso, finalizar_etl_erro,
)

DIR_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados_externos")

BLOCOS_PLAN2 = [
    ("acidentes_folga_bombeiro", "acidentes de trânsito com bombeiros na folga"),
    ("acidentes_viatura_vitima", "acidentes envolvendo viatura com vítima"),
    ("reclamacoes_denuncias",    "reclamações/denúncias"),
]

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _norm(s):
    return str(s).strip().lower() if s is not None else ""


TIPOS_NORM = {
    "pd": "PD",
    "ipm": "IPM",
    "sindicância": "Sindicância",
    "sindicancia": "Sindicância",
    "inv preliminar": "Inv Preliminar",
    "investigação preliminar": "Inv Preliminar",
    "investigacao preliminar": "Inv Preliminar",
}


# Padroniza vocabulário de situação — "Encerrado" e "Sim" viram "Finalizado"
SITUACAO_NORM = {
    "encerrado":  "Finalizado",
    "finalizado": "Finalizado",
    "sim":        "Finalizado",
    "andamento":  "Andamento",
}


def _norm_tipo(s):
    key = _norm(s)
    return TIPOS_NORM.get(key, s.strip() if s else None)


def _norm_situacao(s):
    key = _norm(s)
    return SITUACAO_NORM.get(key, s.strip() if s else None)


def _title_pt(s):
    """Title-case respeitando preposições/artigos comuns em pt-BR."""
    if not s: return None
    partes = s.strip().split()
    minusc = {"de","da","do","das","dos","e","em","com","a","o","à","às","ao","aos","em","por","para"}
    out = []
    for i, p in enumerate(partes):
        if i > 0 and p.lower() in minusc:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def _sha256(items):
    """Hash estável dos campos identificadores da linha (deduplicação)."""
    key = "|".join(str(x or "") for x in items)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# --------- LEITURA ---------
def ler_plan1(ws):
    """Retorna [(data_abertura, titulo, tipo, interessado, unidade, punicao, finalizado)]."""
    linhas = []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1 or not row or not row[0]:
            continue
        data_abr = row[0].date() if hasattr(row[0], "date") else None
        if data_abr is None:
            continue
        linhas.append((
            data_abr,
            _title_pt(row[1]) if row[1] else None,
            _norm_tipo(row[2]),
            _title_pt(row[3]) if row[3] else None,
            _norm(row[4]).upper() if row[4] else None,
            _title_pt(row[5]) if row[5] else None,
            _norm_situacao(row[6]),
        ))
    return linhas


def ler_plan2(ws, ano):
    """Retorna [(indicador, ano, mes, valor)]."""
    linhas = list(ws.iter_rows(values_only=True))
    saida = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        titulo = _norm(linha[0]) if linha else ""
        chave = None
        for k, rotulo in BLOCOS_PLAN2:
            if rotulo in titulo:
                chave = k; break
        if not chave:
            i += 1; continue
        if i + 2 >= len(linhas):
            break
        cabecalho = linhas[i + 1]
        valores   = linhas[i + 2]
        meses_cols = [MESES_PT.get(_norm(c)) for c in cabecalho]
        for j, mes in enumerate(meses_cols):
            if mes is None or j >= len(valores):
                continue
            v = valores[j]
            if v is None or str(v).strip() == "":
                continue
            try:
                saida.append((chave, ano, mes, int(v)))
            except (ValueError, TypeError):
                pass
        i += 3
    return saida


# --------- INGESTÃO ---------
def upsert_processos(cur, linhas_plan1, origem_arquivo):
    inseridas, atualizadas = 0, 0
    for row in linhas_plan1:
        data_abr, titulo, tipo, interessado, unidade, punicao, finalizado = row
        sha = _sha256(row)
        cur.execute("""
            INSERT INTO sjd.processos
                (data_abertura, titulo, tipo, interessado, unidade,
                 punicao, finalizado, conteudo_sha256, origem_arquivo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (conteudo_sha256) DO UPDATE
              SET titulo=EXCLUDED.titulo,
                  tipo=EXCLUDED.tipo,
                  interessado=EXCLUDED.interessado,
                  unidade=EXCLUDED.unidade,
                  punicao=EXCLUDED.punicao,
                  finalizado=EXCLUDED.finalizado,
                  origem_arquivo=EXCLUDED.origem_arquivo,
                  atualizado_em=NOW()
            RETURNING (xmax = 0) AS inserido
        """, (data_abr, titulo, tipo, interessado, unidade,
              punicao, finalizado, sha, origem_arquivo))
        inserido = cur.fetchone()[0]
        if inserido: inseridas += 1
        else: atualizadas += 1
    return inseridas, atualizadas


def upsert_indicadores(cur, linhas_plan2):
    inseridas, atualizadas = 0, 0
    for indicador, ano, mes, valor in linhas_plan2:
        cur.execute("""
            INSERT INTO sjd.indicadores_mensais (indicador, ano, mes, valor)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (indicador, ano, mes) DO UPDATE
              SET valor=EXCLUDED.valor, atualizado_em=NOW()
            RETURNING (xmax = 0) AS inserido
        """, (indicador, ano, mes, valor))
        inserido = cur.fetchone()[0]
        if inserido: inseridas += 1
        else: atualizadas += 1
    return inseridas, atualizadas


def processar_arquivo(cur, caminho):
    """Roda o ETL sobre um único xlsx. Extrai o ano do nome do arquivo."""
    nome = os.path.basename(caminho)
    # sjd_<ano>-S<sem>.xlsx
    ano = None
    for tok in nome.replace("-", "_").split("_"):
        if tok.isdigit() and len(tok) == 4:
            ano = int(tok); break
    if ano is None:
        ano = date.today().year

    wb = openpyxl.load_workbook(caminho, data_only=True)
    p1 = ler_plan1(wb["Plan1"]) if "Plan1" in wb.sheetnames else []
    p2 = ler_plan2(wb["Plan2"], ano) if "Plan2" in wb.sheetnames else []

    ins_p, upd_p = upsert_processos(cur, p1, nome)
    ins_i, upd_i = upsert_indicadores(cur, p2)

    print(f"  {nome}: processos {ins_p}i/{upd_p}u | indicadores {ins_i}i/{upd_i}u")
    return len(p1) + len(p2), ins_p + ins_i, upd_p + upd_i


def main():
    # Padrão: substitui tudo (semântica de "reprocessar o xlsx"). --append pra só somar.
    append = "--append" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--append"]

    if args:
        arquivos = [args[0]]
    else:
        arquivos = sorted(glob.glob(os.path.join(DIR_DADOS, "sjd_*.xlsx")))
        if not arquivos:
            print("!! nenhum sjd_*.xlsx em", DIR_DADOS)
            return

    conn = conectar_postgres()
    cur = conn.cursor()
    etl_id = None
    try:
        etl_id = iniciar_etl(cur, "sjd")
        if not append:
            cur.execute("TRUNCATE sjd.processos, sjd.indicadores_mensais")
            print(">> modo REPLACE: tabelas zeradas antes da carga")

        total_lidas = total_ins = total_upd = 0
        for arq in arquivos:
            l, i, u = processar_arquivo(cur, arq)
            total_lidas += l; total_ins += i; total_upd += u
        finalizar_etl_sucesso(cur, etl_id, total_lidas, total_ins, total_upd)
        conn.commit()
        print(f">> OK — lidas={total_lidas} inseridas={total_ins} atualizadas={total_upd}")
    except Exception as e:
        conn.rollback()
        if etl_id:
            finalizar_etl_erro(cur, etl_id, str(e))
            conn.commit()
        print(f"!! FALHOU: {e}")
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
