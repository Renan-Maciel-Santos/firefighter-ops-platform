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

router = APIRouter(prefix="/elogios", tags=["elogios"])

ABA = "elogios"

ORDEM_SGB = ["SEDE", "1° SGB", "2° SGB", "3° SGB", "4° SGB", "COBOM", "SAT"]


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/resumo")
def resumo_elogios(
    ano: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    filtro_ano = "AND ano = :ano" if ano else ""
    params = {"ano": ano} if ano else {}

    # Totais gerais
    geral = db.execute(text(f"""
        SELECT
            COUNT(*)                                    AS total,
            COUNT(*) FILTER (WHERE tipo = 'ELO')        AS elogios,
            COUNT(*) FILTER (WHERE tipo = 'LMP')        AS lmp,
            COUNT(*) FILTER (WHERE tipo = 'LOU')        AS louvor
        FROM b5.elogios
        WHERE 1=1 {filtro_ano}
    """), params).mappings().first()

    # Por SGB
    por_sgb = db.execute(text(f"""
        SELECT
            sgb,
            COUNT(*)                                    AS total,
            COUNT(*) FILTER (WHERE tipo = 'ELO')        AS elogios,
            COUNT(*) FILTER (WHERE tipo = 'LMP')        AS lmp,
            COUNT(*) FILTER (WHERE tipo = 'LOU')        AS louvor
        FROM b5.elogios
        WHERE sgb IS NOT NULL {filtro_ano}
        GROUP BY sgb
        ORDER BY sgb
    """), params).mappings().all()

    # Anos disponíveis para filtro
    anos = [r[0] for r in db.execute(
        text("SELECT DISTINCT ano FROM b5.elogios WHERE ano IS NOT NULL ORDER BY ano DESC")
    ).fetchall()]

    return {
        "geral": dict(geral),
        "por_sgb": [dict(r) for r in por_sgb],
        "anos": anos,
        "por_militar": elogios_por_militar(db, geral, por_sgb),
    }


# Acima: Lotação do efetivo (vw_efetivo_classificado) → rótulo de unidade dos elogios
LOTACAO_PARA_SGB = {"EM": "SEDE", "1°Sgb": "1° SGB", "2°Sgb": "2° SGB",
                    "3°Sgb": "3° SGB", "4°Sgb": "4° SGB"}


def elogios_por_militar(db, geral, por_sgb):
    """Elogios (tipo ELO) divididos pelo efetivo existente. LMP e louvor não entram.

    O efetivo é o do último dia em b1.efetivo_quantitativo_diario. Elogio
    sem unidade (sgb nulo) entra no índice da unidade inteira, não no de nenhum SGB.
    """
    linhas = db.execute(text("""
        SELECT data_referencia, lotacao, quantidade
          FROM b1.vw_efetivo_quantitativo_lotacao
         WHERE data_referencia = (SELECT max(data_referencia) FROM b1.efetivo_quantitativo_diario)
    """)).mappings().all()
    if not linhas:
        return None

    efetivo = {LOTACAO_PARA_SGB.get(l["lotacao"], l["lotacao"]): l["quantidade"] for l in linhas}
    total_efetivo = sum(efetivo.values())
    por_unidade = {r["sgb"]: r["elogios"] for r in por_sgb}

    def indice(elogios, militares):
        return round(elogios / militares, 2) if militares else None

    return {
        "efetivo_em": linhas[0]["data_referencia"].isoformat(),
        "unidade": {
            "elogios": geral["elogios"],
            "efetivo": total_efetivo,
            "indice": indice(geral["elogios"], total_efetivo),
        },
        "por_sgb": [
            {"sgb": sgb,
             "elogios": por_unidade.get(sgb, 0),
             "efetivo": efetivo.get(sgb, 0),
             "indice": indice(por_unidade.get(sgb, 0), efetivo.get(sgb, 0))}
            for sgb in ORDEM_SGB if sgb in efetivo
        ],
    }


@router.get("/lista")
def listar_elogios(
    sgb: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    ano: Optional[int] = Query(None),
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    base = "FROM b5.elogios WHERE 1=1"
    params = {}

    if sgb:
        base += " AND sgb = :sgb"
        params["sgb"] = sgb
    if tipo:
        base += " AND tipo = :tipo"
        params["tipo"] = tipo
    if ano:
        base += " AND ano = :ano"
        params["ano"] = ano
    if busca:
        base += " AND (nome ILIKE :busca OR re ILIKE :busca)"
        params["busca"] = f"%{busca}%"

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
    offset = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT nbi, num_bi_11gb, posto_grad, re, nome,
               assunto, tipo, data_lancamento, sgb,
               solenidade, observacoes, mes_ano
        {base}
        ORDER BY data_lancamento DESC NULLS LAST, nbi DESC
        LIMIT {limit} OFFSET {offset}
    """), params).mappings().all()

    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}
