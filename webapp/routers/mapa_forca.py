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

router = APIRouter(prefix="/mapa-forca", tags=["mapa-forca"])

ABA = "mapa"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


def _latest_snapshot_id(db: Session) -> Optional[int]:
    return db.execute(text(
        "SELECT id FROM b3.mapa_forca_snapshot_raw "
        "ORDER BY data_servico DESC NULLS LAST, capturado_em DESC LIMIT 1"
    )).scalar()


@router.get("/resumo")
def resumo_snapshot(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    sid = _latest_snapshot_id(db)
    if not sid:
        return {"snapshot": None, "geral": {}, "por_sgb": []}

    snap = db.execute(text("""
        SELECT id, data_servico, capturado_em, cabecalho_texto
        FROM b3.mapa_forca_snapshot_raw WHERE id = :sid
    """), {"sid": sid}).mappings().first()

    # Viaturas e efetivo vêm da linha; água e mergulhadores são da estação
    # (na planilha são células mescladas sobre todo o grupo do quartel).
    viaturas = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE situacao = 'OPERANDO') AS viaturas_operando,
            COUNT(*) FILTER (WHERE situacao = 'RESERVA')  AS viaturas_reserva,
            COUNT(*) FILTER (WHERE situacao = 'BAIXADA')  AS viaturas_baixadas,
            COUNT(*)                                       AS viaturas_total,
            COALESCE(SUM(efetivo_qtd), 0)                 AS efetivo_total
        FROM b3.mapa_forca_linha WHERE snapshot_id = :sid
    """), {"sid": sid}).mappings().first()

    estacoes = db.execute(text("""
        SELECT
            COUNT(*)                                      AS estacoes_total,
            COALESCE(SUM(capacidade_agua_l), 0)           AS agua_total_litros,
            COALESCE(SUM(mergulhadores), 0)               AS mergulhadores_total
        FROM b3.mapa_forca_estacao WHERE snapshot_id = :sid
    """), {"sid": sid}).mappings().first()

    geral = {**dict(viaturas), **dict(estacoes)}

    por_sgb_viaturas = db.execute(text("""
        SELECT
            bloco_nome,
            COUNT(*) FILTER (WHERE situacao = 'OPERANDO') AS operando,
            COUNT(*) FILTER (WHERE situacao = 'RESERVA')  AS reserva,
            COUNT(*) FILTER (WHERE situacao = 'BAIXADA')  AS baixada,
            COALESCE(SUM(efetivo_qtd), 0)                 AS efetivo
        FROM b3.mapa_forca_linha WHERE snapshot_id = :sid
        GROUP BY bloco_nome
    """), {"sid": sid}).mappings().all()

    por_sgb_estacoes = db.execute(text("""
        SELECT
            bloco_nome,
            COUNT(*)                                      AS estacoes,
            COALESCE(SUM(capacidade_agua_l), 0)           AS agua_litros,
            COALESCE(SUM(mergulhadores), 0)               AS mergulhadores
        FROM b3.mapa_forca_estacao WHERE snapshot_id = :sid
        GROUP BY bloco_nome
    """), {"sid": sid}).mappings().all()

    agregado: dict = {}
    for r in por_sgb_viaturas:
        agregado[r["bloco_nome"]] = dict(r)
    for r in por_sgb_estacoes:
        agregado.setdefault(r["bloco_nome"], {"bloco_nome": r["bloco_nome"]}).update(dict(r))

    por_sgb = [agregado[k] for k in sorted(agregado)]

    return {
        "snapshot": dict(snap),
        "geral": geral,
        "por_sgb": por_sgb,
    }


@router.get("/estacoes")
def listar_estacoes(
    bloco: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Estações do último snapshot, com a capacidade de água e os mergulhadores
    do quartel. Esses dois números são do quartel inteiro, não de uma viatura.
    """
    check_access(current_user)
    sid = _latest_snapshot_id(db)
    if not sid:
        return {"total": 0, "data": []}

    params = {"sid": sid}
    if bloco:
        params["bloco"] = bloco

    rows = db.execute(text(f"""
        SELECT e.id, e.bloco_nome, e.estacao_nome, e.estacao_codigo, e.estacao_telefone,
               e.capacidade_agua_l, e.mergulhadores,
               (SELECT COUNT(*) FROM b3.mapa_forca_linha l WHERE l.estacao_id = e.id) AS viaturas,
               (SELECT COUNT(*) FROM b3.mapa_forca_linha l
                 WHERE l.estacao_id = e.id AND l.situacao = 'OPERANDO')                AS viaturas_operando,
               (SELECT COALESCE(SUM(l.efetivo_qtd), 0) FROM b3.mapa_forca_linha l
                 WHERE l.estacao_id = e.id)                                            AS efetivo
        FROM b3.mapa_forca_estacao e
        WHERE e.snapshot_id = :sid
        {"AND e.bloco_nome = :bloco" if bloco else ""}
        ORDER BY e.bloco_nome, e.ordem
    """), params).mappings().all()

    return {"total": len(rows), "data": [dict(r) for r in rows]}


@router.get("/linhas")
def listar_linhas(
    bloco: Optional[str] = Query(None),
    situacao: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    sid = _latest_snapshot_id(db)
    if not sid:
        return {"total": 0, "page": page, "limit": limit, "data": []}

    base = "FROM b3.mapa_forca_linha WHERE snapshot_id = :sid"
    params = {"sid": sid}

    if bloco:
        base += " AND bloco_nome = :bloco"
        params["bloco"] = bloco
    if situacao:
        base += " AND situacao = :situacao"
        params["situacao"] = situacao
    if busca:
        base += " AND (viatura ILIKE :busca OR estacao_bombeiros ILIKE :busca OR militar_e_telefone ILIKE :busca)"
        params["busca"] = f"%{busca}%"

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
    offset = (page - 1) * limit

    # Água e mergulhadores não saem aqui de propósito: são da estação, não da
    # viatura. Use /mapa-forca/estacoes para esses números.
    rows = db.execute(text(f"""
        SELECT viatura, bloco_nome,
               TRIM(estacao_bombeiros) AS estacao_bombeiros,
               situacao, efetivo_qtd, posto_graduacao,
               militar_e_telefone
        {base}
        ORDER BY bloco_nome, ordem, viatura
        LIMIT {limit} OFFSET {offset}
    """), params).mappings().all()

    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}
