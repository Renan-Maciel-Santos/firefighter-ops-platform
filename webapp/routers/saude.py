from datetime import date

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

router = APIRouter(prefix="/saude", tags=["saude"])

ABA = "saude"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/resumo")
def resumo_saude(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)

    rows = db.execute(text("SELECT * FROM b1.vw_ias_percentual")).mappings().all()
    ias = {r["situacao_ias"]: {"quantidade": r["quantidade"], "percentual": float(r["percentual"])} for r in rows}

    total = db.execute(text("SELECT COUNT(*) FROM b1.efetivo WHERE ativo")).scalar()

    afastados = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE r.observacao = 'Apto com Restrição')                                    AS restricao,
            COUNT(*) FILTER (WHERE r.observacao IN ('Licença para tratamento de saúde', 'Licença Gestante')) AS lts
        FROM b1.restricoes r
        JOIN b1.efetivo e ON e.re = r.re AND e.ativo = true
        WHERE r.observacao != 'Apto Pleno'
          AND (r.data_final IS NULL OR r.data_final >= CURRENT_DATE)
    """)).mappings().first()

    total_f = float(total) if total else 1.0
    qtd_restricao = int(afastados["restricao"] or 0)
    qtd_lts       = int(afastados["lts"]       or 0)

    # Apto sem restrição no último ano fechado (o anterior ao corrente)
    ANO_REFERENCIA = date.today().year - 1
    com_restricao = db.execute(text("""
        SELECT COUNT(DISTINCT r.re) AS qtd
        FROM b1.restricoes r
        JOIN b1.efetivo e ON e.re = r.re AND e.ativo = true
        WHERE r.observacao != 'Apto Pleno'
          AND r.data_inicial <= MAKE_DATE(:ano, 12, 31)
          AND (r.data_final IS NULL OR r.data_final >= MAKE_DATE(:ano, 1, 1));
    """), {"ano": ANO_REFERENCIA}).scalar() or 0
    apto_sem_restricao = int(total) - int(com_restricao)

    return {
        "total_ativos": total,
        "ias": ias,
        "restricao": {
            "quantidade": qtd_restricao,
            "percentual": round(100 * qtd_restricao / total_f, 1),
        },
        "lts": {
            "quantidade": qtd_lts,
            "percentual": round(100 * qtd_lts / total_f, 1),
        },
        "apto_ano": {
            "ano":             ANO_REFERENCIA,
            "quantidade":      apto_sem_restricao,
            "com_restricao":   int(com_restricao),
            "percentual":      round(100 * apto_sem_restricao / total_f, 1),
        },
    }


@router.get("/restricoes")
def listar_restricoes(
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    base = """
        FROM b1.restricoes r
        JOIN b1.vw_efetivo_classificado e ON e.re = r.re AND e.ativo = true
        WHERE r.observacao != 'Apto Pleno'
          AND (r.data_final IS NULL OR r.data_final >= CURRENT_DATE)
          -- Acima: Quem tem restrição vigente não precisa aparecer também com a supervisão CAPS/NAPS
          -- (a restrição é o dado operacional). Quem só tem supervisão continua listado normalmente.
          -- Acima: left()/upper() em vez de ILIKE 'SUPERVIS%' pra não depender de escape de '%' no text()
          AND NOT (
            left(upper(r.observacao), 8) = 'SUPERVIS'
            AND EXISTS (
              SELECT 1 FROM b1.restricoes r2
              WHERE r2.re = r.re
                AND r2.observacao = 'Apto com Restrição'
                AND (r2.data_final IS NULL OR r2.data_final >= CURRENT_DATE)
            )
          )
    """
    params = {}
    if busca:
        base += " AND (e.nome ILIKE :busca OR r.re::text ILIKE :busca)"
        params["busca"] = f"%{busca}%"

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
    offset = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT r.re, e.nome, e.posto_grad, e.lotacao,
               CASE
                 WHEN r.observacao = 'Apto com Restrição' THEN 'Restrição'
                 WHEN r.observacao IN ('Licença para tratamento de saúde', 'Licença Gestante') THEN 'LTS'
                 ELSE r.observacao
               END AS tipo,
               r.restricao_medica AS restricoes,
               r.data_inicial     AS data_inicio,
               r.data_final       AS data_termino,
               r.total_dias       AS dias,
               NULL::text         AS recolher_arma
        {base}
        ORDER BY r.data_final NULLS FIRST, e.nome
        LIMIT {limit} OFFSET {offset}
    """), params).mappings().all()

    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}
