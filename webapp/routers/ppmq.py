from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user
from fastapi import HTTPException

router = APIRouter(prefix="/ppmq", tags=["ppmq"])

ABA = "ppmq"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


# Os cartões do painel são um por SGB mais o total da unidade. As views
# b4.vw_ppmq_* só devolvem o total; aqui a mesma fórmula é aberta por SGB
# (GROUPING SETS), e a linha sem SGB vira o total. Viatura da sede, fora de
# SGB, entra só no total.
_SGB_OU_TOTAL = "CASE WHEN GROUPING(sgb) = 1 THEN '11º GB' ELSE sgb END"


@router.get("/taxa-baixadas")
def taxa_baixadas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    # Acima: Mesma regra de b4.vw_ppmq_taxa_baixadas — baixada e em descarga
    # contam como baixadas; o denominador exclui locadas e N/P.
    rows = db.execute(text(f"""
        SELECT {_SGB_OU_TOTAL} AS sgb,
               count(*) AS total_viaturas,
               count(*) FILTER (WHERE status IN ('BAIXADA', 'BAIXADA_DESCARGA')) AS baixadas,
               round(100.0 * count(*) FILTER (WHERE status IN ('BAIXADA', 'BAIXADA_DESCARGA'))
                     / NULLIF(count(*) FILTER (WHERE proprietario NOT IN ('LOCADA', 'N/P')), 0), 2)
                   AS pct_baixadas
        FROM b4.viaturas
        WHERE sgb IS NOT NULL
        GROUP BY GROUPING SETS ((sgb), ())
        HAVING GROUPING(sgb) = 1 OR sgb LIKE '%SGB'
        ORDER BY GROUPING(sgb), sgb
    """)).mappings().all()
    return {"meta": 20, "data": [dict(r) for r in rows]}


@router.get("/idade-media")
def idade_media(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    # Acima: Mesma regra de b4.vw_ppmq_idade_media (ano corrente - ano de fabricação).
    rows = db.execute(text(f"""
        SELECT {_SGB_OU_TOTAL} AS sgb,
               count(*) AS total_viaturas,
               round(avg(extract(year FROM current_date) - ano_fabricacao), 2) AS idade_media,
               count(*) FILTER (WHERE extract(year FROM current_date) - ano_fabricacao > 15)
                   AS viaturas_acima_15anos
        FROM b4.viaturas
        WHERE sgb IS NOT NULL AND ano_fabricacao IS NOT NULL
        GROUP BY GROUPING SETS ((sgb), ())
        HAVING GROUPING(sgb) = 1 OR sgb LIKE '%SGB'
        ORDER BY GROUPING(sgb), sgb
    """)).mappings().all()
    return {"meta": 15, "data": [dict(r) for r in rows]}
