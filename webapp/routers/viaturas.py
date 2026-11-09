from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user

router = APIRouter(prefix="/viaturas", tags=["viaturas"])

ABA = "viaturas"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/")
def listar_viaturas(
    sgb: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    base_query = "SELECT * FROM b4.vw_viaturas_situacao WHERE 1=1"
    params = {}

    if sgb:
        base_query += " AND sgb = :sgb"
        params["sgb"] = sgb
    if status:
        base_query += " AND status = :status"
        params["status"] = status
    if tipo:
        base_query += " AND tipo = :tipo"
        params["tipo"] = tipo

    count_query = f"SELECT COUNT(*) FROM ({base_query}) t"
    total = db.execute(text(count_query), params).scalar()

    offset = (page - 1) * limit
    data_query = base_query + f" LIMIT {limit} OFFSET {offset}"
    rows = db.execute(text(data_query), params).mappings().all()

    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}


@router.get("/resumo")
def resumo_viaturas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    q = """
        SELECT
            COUNT(*)                                                                      AS total,
            COUNT(*) FILTER (WHERE status = 'OPERANDO')                                  AS operando,
            COUNT(*) FILTER (WHERE status = 'BAIXADA')                                   AS baixada,
            COUNT(*) FILTER (WHERE status IN ('BAIXADA_DESCARGA', 'PROC_DESCARGA'))      AS descarga,
            ROUND(AVG(idade_anos) FILTER (WHERE idade_anos IS NOT NULL), 1)              AS idade_media,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE status = 'BAIXADA')
                / NULLIF(COUNT(*), 0)
            , 1)                                                                          AS pct_baixadas
        FROM b4.vw_viaturas_situacao
    """
    row = db.execute(text(q)).mappings().first()
    return dict(row)


@router.get("/filtros")
def filtros_disponiveis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    sgbs = [r[0] for r in db.execute(text("SELECT DISTINCT sgb FROM b4.vw_viaturas_situacao ORDER BY sgb")).fetchall()]
    tipos = [r[0] for r in db.execute(text("SELECT DISTINCT tipo FROM b4.vw_viaturas_situacao ORDER BY tipo")).fetchall()]
    statuses = [r[0] for r in db.execute(text("SELECT DISTINCT status FROM b4.vw_viaturas_situacao ORDER BY status")).fetchall()]
    return {"sgbs": sgbs, "tipos": tipos, "statuses": statuses}


# =====================================================================
# COMPLEMENTOS (09/11/2026) — disponibilidade, uso, histórico, cadastro e
# custo. Tudo cruzado pelo prefixo NORMALIZADO: a frota (b4) grava "AB-11103",
# as capturas do nível operacional e o tempo-resposta gravam "AB11103".
# =====================================================================
from datetime import date

NORM = "regexp_replace(upper({}), '[^A-Z0-9]', '', 'g')"

# Prefixo físico da viatura numa linha da captura do nível operacional. Viatura
# baixada vem SEM viatura_prefixo — o prefixo fica em `us`. Usar só
# viatura_prefixo esconderia exatamente as baixas.
VTR_CAPTURA = NORM.format("COALESCE(v.viatura_prefixo, CASE WHEN v.us ~ '^[A-Z]+[0-9]{5}$' THEN v.us END)")

# Entre duas capturas (~30 min) a situação vale até a próxima. Buraco maior que
# 2 h é captura falhada, não tempo na situação — limita para não inflar.
OBS_CTE = f"""
    cap AS (
        SELECT id, capturado_em FROM b3.nivel_op_captura
        WHERE capturado_em >= NOW() - make_interval(days => :dias)
    ),
    obs AS (
        SELECT DISTINCT ON (c.id, {VTR_CAPTURA})
               {VTR_CAPTURA} AS vtr, c.capturado_em AS em, v.status, v.status_grp AS grp
        FROM b3.nivel_op_viatura v JOIN cap c ON c.id = v.captura_id
        WHERE {VTR_CAPTURA} <> ''
        ORDER BY c.id, {VTR_CAPTURA}, v.status_grp
    ),
    frota AS (
        SELECT prefixo, {NORM.format('prefixo')} AS vtr, sgb, tipo, idade_anos, nome_estacao,
               status AS status_frota
        FROM b4.vw_viaturas_situacao
    ),
    seq AS (
        SELECT o.*, f.prefixo, f.sgb, f.tipo, f.idade_anos, f.status_frota,
               LEAST(EXTRACT(EPOCH FROM (LEAD(o.em) OVER w - o.em)) / 3600.0, 2) AS horas,
               LAG(o.grp) OVER w AS grp_ant
        FROM obs o JOIN frota f USING (vtr)
        WINDOW w AS (PARTITION BY o.vtr ORDER BY o.em)
    )
"""
SGB_DIGITO = r"substring({} from '\d')"


def _num(r):
    return {k: (float(v) if hasattr(v, "is_finite") else v) for k, v in dict(r).items()}


@router.get("/disponibilidade")
def disponibilidade(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """% do tempo operando / reserva / baixada de cada viatura, e a série diária por SGB."""
    check_access(current_user)
    p = {"dias": dias}

    por_vtr = db.execute(text(f"""
        WITH {OBS_CTE}
        SELECT prefixo, sgb, tipo, idade_anos, status_frota,
               ROUND(100.0 * COALESCE(SUM(horas) FILTER (WHERE grp = 'O'), 0) / NULLIF(SUM(horas), 0), 1) AS pct_operando,
               ROUND(100.0 * COALESCE(SUM(horas) FILTER (WHERE grp = 'R'), 0) / NULLIF(SUM(horas), 0), 1) AS pct_reserva,
               ROUND(100.0 * COALESCE(SUM(horas) FILTER (WHERE grp = 'B'), 0) / NULLIF(SUM(horas), 0), 1) AS pct_baixada,
               ROUND((COALESCE(SUM(horas) FILTER (WHERE grp = 'B'), 0) / 24.0)::numeric, 1)  AS dias_baixada,
               COUNT(*) FILTER (WHERE grp = 'B' AND grp_ant IS DISTINCT FROM 'B' AND grp_ant IS NOT NULL) AS baixas,
               ROUND((SUM(horas) / 24.0)::numeric, 1) AS dias_observados
        FROM seq
        GROUP BY prefixo, sgb, tipo, idade_anos, status_frota
        HAVING SUM(horas) > 0
        ORDER BY pct_baixada DESC NULLS LAST, baixas DESC
    """), p).mappings().all()

    # Série diária: média, nas capturas do dia, de quantas viaturas de cada
    # SGB estavam em cada grupo.
    serie = db.execute(text(f"""
        WITH {OBS_CTE},
        por_cap AS (
            SELECT o.em, f.sgb,
                   COUNT(*) FILTER (WHERE o.grp = 'O') AS o,
                   COUNT(*) FILTER (WHERE o.grp = 'R') AS r,
                   COUNT(*) FILTER (WHERE o.grp = 'B') AS b
            FROM obs o JOIN frota f USING (vtr)
            GROUP BY o.em, f.sgb
        )
        SELECT (em AT TIME ZONE 'America/Sao_Paulo')::date AS dia, sgb,
               ROUND(AVG(o), 1) AS operando, ROUND(AVG(r), 1) AS reserva, ROUND(AVG(b), 1) AS baixada
        FROM por_cap GROUP BY 1, 2 ORDER BY 1, 2
    """), p).mappings().all()

    primeira = db.execute(text("SELECT MIN(capturado_em)::date FROM b3.nivel_op_captura")).scalar()
    return {
        "dias": dias,
        "primeira_captura": primeira,
        "viaturas": [_num(r) for r in por_vtr],
        "serie": [_num(r) for r in serie],
    }


@router.get("/uso")
def uso(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Atendimentos por viatura e ano, com idade e tipo da frota.

    Tempos são MEDIANAS sobre b3.vw_tempo_resposta_valido (descarta tempos
    negativos ou acima de 10 h), como na aba Ocorrências.
    """
    check_access(current_user)
    linhas = db.execute(text(f"""
        WITH frota AS (
            SELECT prefixo, {NORM.format('prefixo')} AS vtr, sgb, tipo, idade_anos, status
            FROM b4.vw_viaturas_situacao
        )
        SELECT f.prefixo, f.sgb, f.tipo, f.idade_anos, f.status,
               EXTRACT(YEAR FROM t.dt_ocorrencia)::int AS ano,
               COUNT(t.*) AS atendimentos,
               ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.t_total_min))::numeric, 1)        AS t_resposta_min,
               ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.t_deslocamento_min))::numeric, 1) AS t_deslocamento_min
        FROM frota f
        LEFT JOIN b3.vw_tempo_resposta_valido t ON {NORM.format('t.viatura')} = f.vtr
        GROUP BY 1, 2, 3, 4, 5, 6
    """)).mappings().all()
    ultimo = db.execute(text("SELECT MAX(dt_ocorrencia)::date FROM b3.tempo_resposta")).scalar()

    vtrs = {}
    for r in linhas:
        v = vtrs.setdefault(r["prefixo"], {
            "prefixo": r["prefixo"], "sgb": r["sgb"], "tipo": r["tipo"],
            "idade_anos": r["idade_anos"], "status": r["status"], "por_ano": {},
        })
        if r["ano"]:
            v["por_ano"][r["ano"]] = {
                "atendimentos": r["atendimentos"],
                "t_resposta_min": float(r["t_resposta_min"]) if r["t_resposta_min"] is not None else None,
                "t_deslocamento_min": float(r["t_deslocamento_min"]) if r["t_deslocamento_min"] is not None else None,
            }
    anos = sorted({a for v in vtrs.values() for a in v["por_ano"]})
    return {"ultimo_dado": ultimo, "anos": anos, "viaturas": list(vtrs.values())}


@router.get("/historico/{prefixo}")
def historico(
    prefixo: str,
    dias: int = Query(365, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Linha do tempo de uma viatura: períodos em cada situação e trocas do SIOPM."""
    check_access(current_user)
    p = {"dias": dias, "vtr": "".join(ch for ch in prefixo.upper() if ch.isalnum())}

    cad = db.execute(text(f"""
        SELECT * FROM b4.vw_viaturas_situacao WHERE {NORM.format('prefixo')} = :vtr
    """), p).mappings().first()
    if not cad:
        raise HTTPException(404, "Viatura não encontrada na frota")

    # Capturas consecutivas na mesma situação viram um período só.
    periodos = db.execute(text(f"""
        WITH {OBS_CTE},
        uma AS (SELECT * FROM obs WHERE vtr = :vtr),
        marc AS (
            SELECT *, CASE WHEN status IS DISTINCT FROM LAG(status) OVER (ORDER BY em) THEN 1 ELSE 0 END AS novo
            FROM uma
        ),
        blocos AS (SELECT *, SUM(novo) OVER (ORDER BY em) AS bloco FROM marc)
        SELECT status, MIN(grp) AS grp, MIN(em) AS inicio, MAX(em) AS ultimo_visto
        FROM blocos GROUP BY bloco, status ORDER BY inicio DESC
    """), p).mappings().all()

    trocas = db.execute(text(f"""
        SELECT executado_em, campo, antes, depois FROM b4.viaturas_sync_siopm
        WHERE {NORM.format('prefixo')} = :vtr ORDER BY executado_em DESC LIMIT 200
    """), p).mappings().all()

    return {
        "cadastro": _num(cad),
        "periodos": [dict(r) for r in periodos],
        "trocas": [dict(r) for r in trocas],
    }


# Campos que a B/4 precisa ter preenchidos na planilha de origem.
CAMPOS_CADASTRO = {
    "placa": "Placa", "modelo": "Modelo", "fabricante": "Fabricante",
    "ano_fabricacao": "Ano de fabricação", "proprietario": "Proprietário",
    "tipo": "Tipo",
}
# patrimonio_estado fica de fora: em 09/11/2026 estava vazio nas 144 viaturas —
# a planilha de origem não tem a coluna preenchida, e listá-la poluiria tudo.


@router.get("/cadastro-incompleto")
def cadastro_incompleto(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    linhas = db.execute(text("""
        SELECT prefixo, sgb, nome_estacao, status, placa, modelo, fabricante, ano_fabricacao,
               proprietario, tipo
        FROM b4.vw_viaturas_situacao ORDER BY sgb, prefixo
    """)).mappings().all()
    vazio = lambda v: v is None or (isinstance(v, str) and not v.strip())
    saida = []
    for r in linhas:
        faltam = [rot for campo, rot in CAMPOS_CADASTRO.items() if vazio(r[campo])]
        if faltam:
            saida.append({"prefixo": r["prefixo"], "sgb": r["sgb"], "estacao": r["nome_estacao"],
                          "status": r["status"], "faltam": faltam})
    return {"total_frota": len(linhas), "campos": list(CAMPOS_CADASTRO.values()), "viaturas": saida}


@router.get("/custo-sgb")
def custo_sgb(
    ano: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Manutenção de frota e combustível (Finanças) por viatura de cada SGB.

    Finanças grava "1°SGB" (grau) e a frota "1ºSGB" (ordinal): compara só o dígito.
    """
    check_access(current_user)
    ano = ano or date.today().year
    custo = db.execute(text(f"""
        SELECT {SGB_DIGITO.format('l.sgb')} AS n, g.categoria, SUM(g.valor) AS total,
               COUNT(DISTINCT g.mes) AS meses
        FROM financas.gastos g JOIN financas.locais l ON l.id = g.local_id
        WHERE g.ano = :ano AND g.categoria IN ('manutencao_frota', 'combustivel')
        GROUP BY 1, 2
    """), {"ano": ano}).mappings().all()
    frota = db.execute(text(f"""
        SELECT {SGB_DIGITO.format('sgb')} AS n, sgb, COUNT(*) AS viaturas,
               COUNT(*) FILTER (WHERE status = 'OPERANDO') AS operando
        FROM b4.vw_viaturas_situacao GROUP BY 1, 2 ORDER BY 1
    """)).mappings().all()
    disp = {r["n"]: float(r["pct"]) for r in db.execute(text(f"""
        WITH {OBS_CTE}
        SELECT {SGB_DIGITO.format('sgb')} AS n,
               ROUND(100.0 * SUM(horas) FILTER (WHERE grp IN ('O', 'R')) / NULLIF(SUM(horas), 0), 1) AS pct
        FROM seq GROUP BY 1
    """), {"dias": 30}).mappings().all() if r["pct"] is not None}

    saida = []
    for f in frota:
        c = {r["categoria"]: r for r in custo if r["n"] == f["n"]}
        man = float(c["manutencao_frota"]["total"]) if "manutencao_frota" in c else 0.0
        comb = float(c["combustivel"]["total"]) if "combustivel" in c else 0.0
        meses = max([r["meses"] for r in c.values()] or [0])
        saida.append({
            "sgb": f["sgb"], "viaturas": f["viaturas"], "operando_agora": f["operando"],
            "manutencao": man, "combustivel": comb, "meses_com_lancamento": meses,
            "custo_por_viatura_mes": round((man + comb) / f["viaturas"] / meses, 2) if meses and f["viaturas"] else None,
            "pct_disponivel_30d": disp.get(f["n"]),
        })
    return {"ano": ano, "sgbs": saida}
