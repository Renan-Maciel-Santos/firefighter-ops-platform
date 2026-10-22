"""
Coleta agregada dos dados do banco pra o relatório periódico do 11º GB.

Suporta trimestre e semestre — passa o período pelo carregar_tudo().

Cada função aceita (opcionalmente) o intervalo [inicio, fim] e o retorno
respeita a marcação: 'a_integrar' pra KPIs sem fonte no banco.
"""

import sys, os
from datetime import date
from calendar import monthrange

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _comum import conectar_postgres
import dados_cobom
import dados_sjd


# ==========================================================================
# TOTAL DE MUNICÍPIOS DO VALE DO PARAÍBA (referência oficial)
# ==========================================================================
TOTAL_MUNICIPIOS_VALE = 39


# ==========================================================================
# PERÍODO
# ==========================================================================

def resolver_periodo(tipo, ano, num):
    """
    Devolve (data_inicio, data_fim, label_curto, label_longo) pra:
      resolver_periodo('trimestre', 2026, 3)  → Q3 = 01/jul a 30/set
      resolver_periodo('semestre',  2026, 1)  → S1 = 01/jan a 30/jun
    """
    tipo = tipo.lower()
    if tipo == "trimestre":
        assert 1 <= num <= 4, "trimestre precisa ser 1..4"
        mes_inicio = 3 * (num - 1) + 1
        mes_fim    = mes_inicio + 2
        label_curto = f"{ano}-Q{num}"
        label_longo = f"{num}º Trimestre de {ano}"
    elif tipo == "semestre":
        assert 1 <= num <= 2, "semestre precisa ser 1 ou 2"
        mes_inicio = 6 * (num - 1) + 1
        mes_fim    = mes_inicio + 5
        label_curto = f"{ano}-S{num}"
        label_longo = f"{num}º Semestre de {ano}"
    elif tipo == "anual":
        mes_inicio, mes_fim = 1, 12
        label_curto = str(ano)
        label_longo = f"Exercício {ano}"
    else:
        raise ValueError(f"Tipo inválido: {tipo}")

    ultimo_dia = monthrange(ano, mes_fim)[1]
    return (date(ano, mes_inicio, 1),
            date(ano, mes_fim, ultimo_dia),
            label_curto, label_longo)


# ==========================================================================
# HELPERS
# ==========================================================================

def scalar(cur, sql, params=None):
    cur.execute(sql, params or {})
    r = cur.fetchone()
    return r[0] if r else None


def rows_dict(cur, sql, params=None):
    cur.execute(sql, params or {})
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ==========================================================================
# EFETIVO — total, por SGB, operacional (cod_opm terminado em 1)
# ==========================================================================

def dados_efetivo(cur):
    total_ativos = scalar(cur, "SELECT count(*) FROM b1.efetivo WHERE ativo = true")

    por_lotacao = rows_dict(cur, """
        SELECT lotacao, COUNT(*) AS qtd
        FROM b1.vw_efetivo_classificado
        WHERE ativo = true
        GROUP BY lotacao ORDER BY lotacao
    """)

    # Fonte única de verdade: mesma view que o painel do webapp usa.
    # Regra "operacional" = cod_opm_atual NÃO termina em 0 (só quem termina em 0 é comando/admin).
    todas = rows_dict(cur, """
        SELECT lotacao,
               total_ativos AS total,
               total_operacional AS operacional,
               perc_operacional AS pct
        FROM b1.vw_efetivo_operacional
        ORDER BY CASE lotacao WHEN 'TOTAL GERAL' THEN 999 ELSE 1 END, lotacao
    """)

    operacional_por_sgb = [r for r in todas if r["lotacao"] != "TOTAL GERAL"]
    total_geral_row = next((r for r in todas if r["lotacao"] == "TOTAL GERAL"), None)
    total_geral = {
        "total":       total_geral_row["total"] if total_geral_row else 0,
        "operacional": total_geral_row["operacional"] if total_geral_row else 0,
        "pct":         float(total_geral_row["pct"]) if total_geral_row else 0,
    }

    return {
        "total_ativos":         total_ativos,
        "por_lotacao":          por_lotacao,
        "operacional_por_sgb":  operacional_por_sgb,
        "operacional_geral":    total_geral,
    }


# ==========================================================================
# ABSENTEÍSMO LTS — % em LTS no período
# ==========================================================================

def dados_absenteismo_lts(cur, inicio, fim):
    """Militares que passaram por LTS em algum momento do período, por SGB.
       LTS = observacao contendo 'Licença para tratamento'"""
    por_sgb = rows_dict(cur, """
        WITH em_lts AS (
            SELECT DISTINCT r.re
            FROM b1.restricoes r
            WHERE r.observacao ILIKE '%%tratamento de sa%%'
              AND r.data_inicial <= %(fim)s
              AND (r.data_final IS NULL OR r.data_final >= %(inicio)s)
        )
        SELECT
            v.lotacao,
            COUNT(*) FILTER (WHERE l.re IS NOT NULL) AS em_lts,
            COUNT(*)                                  AS total,
            ROUND(100.0 * COUNT(*) FILTER (WHERE l.re IS NOT NULL)
                / NULLIF(COUNT(*), 0), 2)             AS pct
        FROM b1.vw_efetivo_classificado v
        LEFT JOIN em_lts l ON l.re = v.re
        WHERE v.ativo = true
        GROUP BY v.lotacao ORDER BY v.lotacao
    """, {"inicio": inicio, "fim": fim})

    geral = rows_dict(cur, """
        WITH em_lts AS (
            SELECT DISTINCT r.re
            FROM b1.restricoes r
            WHERE r.observacao ILIKE '%%tratamento de sa%%'
              AND r.data_inicial <= %(fim)s
              AND (r.data_final IS NULL OR r.data_final >= %(inicio)s)
        )
        SELECT
            COUNT(*) FILTER (WHERE l.re IS NOT NULL) AS em_lts,
            COUNT(*)                                  AS total,
            ROUND(100.0 * COUNT(*) FILTER (WHERE l.re IS NOT NULL)
                / NULLIF(COUNT(*), 0), 2)             AS pct
        FROM b1.efetivo e
        LEFT JOIN em_lts l ON l.re = e.re
        WHERE e.ativo = true
    """, {"inicio": inicio, "fim": fim})[0]

    return {"por_sgb": por_sgb, "geral": geral}


# ==========================================================================
# COBERTURA TERRITORIAL — municípios atendidos / 39 municípios do Vale
# ==========================================================================

def dados_cobertura_territorial(cur):
    """Municípios do Vale atendidos pelo 11º GB.
       Fonte: bia.contatos_autorizados nao ajuda; usa mapeamento estação→município
       do último snapshot do mapa força + hardcoded no consulta.py."""
    # Extrai municípios distintos do último snapshot
    sid = scalar(cur, """
        SELECT id FROM b3.mapa_forca_snapshot_raw
        ORDER BY data_servico DESC, capturado_em DESC LIMIT 1
    """)
    municipios_atendidos = 0
    if sid:
        # Tenta descobrir via consulta.py — importa o mapeamento
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "consulta_mod",
                os.path.join(os.path.dirname(__file__), "..", "webapp", "routers", "consulta.py")
            )
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            # Set único de municípios atendidos
            municipios = set(m.ESTACAO_MUNICIPIO.values())
            municipios_atendidos = len(municipios)
        except Exception as e:
            print(f"[aviso] falha ao ler ESTACAO_MUNICIPIO: {e}")

    pct = round(100.0 * municipios_atendidos / TOTAL_MUNICIPIOS_VALE, 1) if municipios_atendidos else 0
    return {
        "total_municipios": TOTAL_MUNICIPIOS_VALE,
        "atendidos": municipios_atendidos,
        "pct": pct,
    }


# ==========================================================================
# ELOGIOS + LMP — por período, por SGB
# ==========================================================================

def dados_elogios_periodo(cur, inicio, fim):
    """Elogios/LMP emitidos no período. Usa data_elogio (ou data_lancamento fallback)."""
    def _query(sgb_filtro):
        return f"""
            SELECT
                COUNT(*)                             AS total,
                COUNT(*) FILTER (WHERE tipo='ELO')   AS elogios,
                COUNT(*) FILTER (WHERE tipo='LMP')   AS lmp,
                COUNT(*) FILTER (WHERE tipo='LOU')   AS louvor
            FROM b5.elogios
            WHERE COALESCE(data_elogio, data_lancamento) BETWEEN %(inicio)s AND %(fim)s
              {sgb_filtro}
        """

    geral = rows_dict(cur, _query(""), {"inicio": inicio, "fim": fim})[0]

    por_sgb = rows_dict(cur, """
        SELECT
            sgb,
            COUNT(*)                             AS total,
            COUNT(*) FILTER (WHERE tipo='ELO')   AS elogios,
            COUNT(*) FILTER (WHERE tipo='LMP')   AS lmp,
            COUNT(*) FILTER (WHERE tipo='LOU')   AS louvor
        FROM b5.elogios
        WHERE COALESCE(data_elogio, data_lancamento) BETWEEN %(inicio)s AND %(fim)s
          AND sgb IS NOT NULL
        GROUP BY sgb ORDER BY sgb
    """, {"inicio": inicio, "fim": fim})

    return {"geral": geral, "por_sgb": por_sgb}


# ==========================================================================
# UGE — processos no período (só Sede — UGE não existe em SGB)
# ==========================================================================

def dados_uge_periodo(cur, inicio, fim):
    """Processos administrativos com atividade no período (ano corrente).
       UGE só existe na Sede."""
    ano_ref = inicio.year
    geral = rows_dict(cur, """
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE status='ANDAMENTO')      AS em_andamento,
            COUNT(*) FILTER (WHERE status='ENCERRADO')      AS encerrado,
            COUNT(*) FILTER (WHERE status='CANCELADO')      AS cancelado,
            COALESCE(SUM(valor_empenhado), 0)               AS total_empenhado,
            COALESCE(SUM(valor_liquidado), 0)               AS total_liquidado,
            COUNT(*) FILTER (
                WHERE status='ANDAMENTO'
                  AND entrega_empenhada IS NOT NULL
                  AND entrega_empenhada < CURRENT_DATE
                  AND (entrega_prorrogada IS NULL OR entrega_prorrogada < CURRENT_DATE)
            ) AS vencidos
        FROM uge.processos
        WHERE ano = %(ano)s
    """, {"ano": ano_ref})[0]

    return {"geral": geral, "ano": ano_ref}


# ==========================================================================
# MOTOMEC — snapshot atual (idade média + baixadas), por SGB
# ==========================================================================

def dados_motomec(cur):
    geral = rows_dict(cur, """
        SELECT
            COUNT(*)                                                          AS total,
            COUNT(*) FILTER (WHERE status='OPERANDO')                         AS operando,
            COUNT(*) FILTER (WHERE status='BAIXADA')                          AS baixada,
            COUNT(*) FILTER (WHERE status IN ('BAIXADA_DESCARGA','PROC_DESCARGA')) AS descarga,
            ROUND(AVG(idade_anos) FILTER (WHERE idade_anos IS NOT NULL), 1)   AS idade_media,
            ROUND(100.0 * COUNT(*) FILTER (WHERE status='BAIXADA')
                / NULLIF(COUNT(*), 0), 1)                                     AS pct_baixadas
        FROM b4.vw_viaturas_situacao
    """)[0]

    por_sgb = rows_dict(cur, """
        SELECT sgb,
               COUNT(*)                                                          AS total,
               COUNT(*) FILTER (WHERE status='OPERANDO')                         AS operando,
               COUNT(*) FILTER (WHERE status='BAIXADA')                          AS baixada,
               COUNT(*) FILTER (WHERE status IN ('BAIXADA_DESCARGA','PROC_DESCARGA')) AS descarga,
               ROUND(AVG(idade_anos) FILTER (WHERE idade_anos IS NOT NULL), 1)   AS idade_media,
               ROUND(100.0 * COUNT(*) FILTER (WHERE status='BAIXADA')
                   / NULLIF(COUNT(*), 0), 1)                                     AS pct_baixadas
        FROM b4.vw_viaturas_situacao
        WHERE sgb IS NOT NULL
        GROUP BY sgb ORDER BY sgb
    """)
    return {"geral": geral, "por_sgb": por_sgb}


# ==========================================================================
# COBOM — vítimas fatais e ocorrências (xlsx externo)
# ==========================================================================

def _coletar_cobom(inicio, fim):
    """Lê o(s) arquivo(s) COBOM cobrindo os meses do período.
       Retorna None se nenhum arquivo estiver disponível."""
    meses_alvo = []
    m = inicio
    while m <= fim:
        meses_alvo.append(m.month)
        prox_mes = m.month + 1
        prox_ano = m.year + (1 if prox_mes > 12 else 0)
        prox_mes = 1 if prox_mes > 12 else prox_mes
        m = date(prox_ano, prox_mes, 1)
    try:
        return dados_cobom.coletar(inicio.year, meses_alvo)
    except Exception as e:
        print(f"[aviso] COBOM indisponível: {e}")
        return None


# ==========================================================================
# SJD — processos disciplinares + indicadores mensais (xlsx externo)
# ==========================================================================

def _coletar_sjd(inicio, fim):
    """Lê o(s) arquivo(s) SJD cobrindo os meses do período."""
    meses_alvo = []
    m = inicio
    while m <= fim:
        meses_alvo.append(m.month)
        prox_mes = m.month + 1
        prox_ano = m.year + (1 if prox_mes > 12 else 0)
        prox_mes = 1 if prox_mes > 12 else prox_mes
        m = date(prox_ano, prox_mes, 1)
    try:
        return dados_sjd.coletar(inicio.year, meses_alvo)
    except Exception as e:
        print(f"[aviso] SJD indisponível: {e}")
        return None


# ==========================================================================
# COLETOR PRINCIPAL
# ==========================================================================

def carregar_tudo(tipo="anual", ano=None, num=1):
    """Retorna dict `dados` com toda a árvore de indicadores + info do período."""
    ano = ano or date.today().year
    inicio, fim, label_curto, label_longo = resolver_periodo(tipo, ano, num)

    conn = conectar_postgres()
    cur = conn.cursor()
    try:
        dados = {
            "periodo": {
                "tipo":         tipo,
                "ano":          ano,
                "num":          num,
                "inicio":       inicio,
                "fim":          fim,
                "label_curto":  label_curto,
                "label_longo":  label_longo,
            },
            "efetivo":     dados_efetivo(cur),
            "absenteismo": dados_absenteismo_lts(cur, inicio, fim),
            "territorio":  dados_cobertura_territorial(cur),
            "elogios":     dados_elogios_periodo(cur, inicio, fim),
            "uge":         dados_uge_periodo(cur, inicio, fim),
            "motomec":     dados_motomec(cur),
            "cobom":       _coletar_cobom(inicio, fim),
            "sjd":         _coletar_sjd(inicio, fim),
        }
    finally:
        cur.close()
        conn.close()

    return dados


if __name__ == "__main__":
    d = carregar_tudo("trimestre", 2026, 3)
    p = d["periodo"]
    print(f"=== {p['label_longo']} ({p['inicio']} a {p['fim']}) ===")
    print()
    print(f"Efetivo total ativo: {d['efetivo']['total_ativos']}")
    print(f"Efetivo operacional geral: {d['efetivo']['operacional_geral']}")
    print(f"Operacional por SGB:")
    for r in d['efetivo']['operacional_por_sgb']:
        print(f"  {r['lotacao']:8s}: {r['operacional']}/{r['total']} ({r['pct']}%)")
    print()
    print(f"Absenteísmo LTS geral: {d['absenteismo']['geral']}")
    print(f"Por SGB:")
    for r in d['absenteismo']['por_sgb']:
        print(f"  {r['lotacao']:8s}: {r['em_lts']}/{r['total']} ({r['pct']}%)")
    print()
    print(f"Cobertura territorial: {d['territorio']['atendidos']}/{d['territorio']['total_municipios']} ({d['territorio']['pct']}%)")
    print()
    print(f"Elogios no período: {d['elogios']['geral']}")
    print(f"UGE no período (ano): {d['uge']['geral']}")
    print()
    print(f"Motomec total: {d['motomec']['geral']}")
