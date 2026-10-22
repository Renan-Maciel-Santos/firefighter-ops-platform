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
