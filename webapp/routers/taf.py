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

router = APIRouter(prefix="/taf", tags=["taf"])

ABA = "taf"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/resumo")
def resumo_taf(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    rows = db.execute(text("SELECT * FROM b1.vw_taf_dashboard ORDER BY situacao_taf")).mappings().all()
    result = {r["situacao_taf"]: {"quantidade": r["quantidade"], "percentual": float(r["percentual"])} for r in rows}
    return result


@router.get("/situacao")
def situacao_taf(
    situacao: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    base = """
        FROM b1.vw_taf_situacao_atual t
        LEFT JOIN b1.vw_efetivo_classificado e ON e.re = t.re
        WHERE 1=1
    """
    params = {}
    if situacao:
        base += " AND t.situacao_taf = :situacao"
        params["situacao"] = situacao
    if busca:
        base += " AND (t.nome ILIKE :busca OR t.re::text ILIKE :busca)"
        params["busca"] = f"%{busca}%"

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
    offset = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT t.re, t.nome, e.posto_grad, e.lotacao,
               t.situacao_taf, t.data_realizado
        {base}
        ORDER BY t.situacao_taf, t.nome
        LIMIT {limit} OFFSET {offset}
    """), params).mappings().all()

    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}


@router.get("/historico")
def historico_taf(
    re: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    rows = db.execute(text("""
        SELECT status, resultado, tipo_taf, data_realizado
        FROM b1.taf_resultados_raw
        WHERE re = :re
        ORDER BY data_realizado DESC
        LIMIT 10
    """), {"re": re}).mappings().all()
    return [dict(r) for r in rows]
