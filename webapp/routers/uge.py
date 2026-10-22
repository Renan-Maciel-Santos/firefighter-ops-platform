from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user

router = APIRouter(prefix="/uge", tags=["uge"])

# Por enquanto liberado a todos os perfis autenticados.
# Quando houver perfil "logistica" / "uge", filtrar aqui.
ABA = "uge"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/resumo")
def resumo_uge(
    ano: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    filtro_ano = "WHERE ano = :ano" if ano else ""
    params = {"ano": ano} if ano else {}

    geral = db.execute(text(f"""
        SELECT
            COUNT(*)                                                  AS total,
            COUNT(*) FILTER (WHERE status = 'ANDAMENTO')              AS em_andamento,
            COUNT(*) FILTER (WHERE status = 'ENCERRADO')              AS encerrado,
            COUNT(*) FILTER (WHERE status = 'CANCELADO')              AS cancelado,
            COALESCE(SUM(valor_empenhado), 0)                         AS total_empenhado,
            COALESCE(SUM(valor_liquidado), 0)                         AS total_liquidado,
            COUNT(*) FILTER (
                WHERE status = 'ANDAMENTO'
                  AND entrega_empenhada IS NOT NULL
                  AND entrega_empenhada < CURRENT_DATE
                  AND (entrega_prorrogada IS NULL OR entrega_prorrogada < CURRENT_DATE)
            )                                                         AS vencidos
        FROM uge.processos
        {filtro_ano}
    """), params).mappings().first()

    por_licitacao = db.execute(text(f"""
        SELECT
            COALESCE(licitacao, 'Não informado') AS licitacao,
            COUNT(*)                              AS qtd,
            COALESCE(SUM(valor_empenhado), 0)    AS empenhado
        FROM uge.processos
        {filtro_ano}
        GROUP BY licitacao ORDER BY empenhado DESC
    """), params).mappings().all()

    por_solicitante = db.execute(text(f"""
        SELECT
            COALESCE(solicitante, 'Não informado') AS solicitante,
            COUNT(*)                                AS qtd,
            COALESCE(SUM(valor_empenhado), 0)      AS empenhado
        FROM uge.processos
        {filtro_ano}
        GROUP BY solicitante ORDER BY empenhado DESC
    """), params).mappings().all()

    por_responsavel = db.execute(text(f"""
        SELECT
            COALESCE(responsavel, 'Não atribuído') AS responsavel,
            COUNT(*)                                AS qtd,
            COUNT(*) FILTER (WHERE status = 'ANDAMENTO') AS em_andamento
        FROM uge.processos
        {filtro_ano}
        GROUP BY responsavel ORDER BY qtd DESC
    """), params).mappings().all()

    anos = [r[0] for r in db.execute(
        text("SELECT DISTINCT ano FROM uge.processos WHERE ano IS NOT NULL ORDER BY ano DESC")
    ).fetchall()]

    return {
        "geral":           dict(geral),
        "por_licitacao":   [dict(r) for r in por_licitacao],
        "por_solicitante": [dict(r) for r in por_solicitante],
        "por_responsavel": [dict(r) for r in por_responsavel],
        "anos":            anos,
    }


@router.get("/processos")
def listar_processos(
    ano:         Optional[int] = Query(None),
    status:      Optional[str] = Query(None),
    licitacao:   Optional[str] = Query(None),
    solicitante: Optional[str] = Query(None),
    responsavel: Optional[str] = Query(None),
    busca:       Optional[str] = Query(None),
    page:        int = Query(1, ge=1),
    limit:       int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)

    base   = "FROM uge.processos WHERE 1=1"
    params = {}
    if ano:         base += " AND ano = :ano";                 params["ano"] = ano
    if status:      base += " AND status = :status";           params["status"] = status
    if licitacao:   base += " AND licitacao = :licitacao";     params["licitacao"] = licitacao
    if solicitante: base += " AND solicitante = :solicitante"; params["solicitante"] = solicitante
    if responsavel: base += " AND responsavel = :responsavel"; params["responsavel"] = responsavel
    if busca:
        base += """ AND (processo_sei ILIKE :busca
                     OR processo_siafem ILIKE :busca
                     OR objeto ILIKE :busca
                     OR ne ILIKE :busca)"""
        params["busca"] = f"%{busca}%"

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
    offset = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT
            numero, processo_sei, processo_siafem, licitacao,
            solicitante, objeto, classe, ne,
            valor_empenhado, valor_liquidado,
            entrega_empenhada, entrega_prorrogada,
            responsavel, status, ano,
            CASE
                WHEN status = 'ANDAMENTO'
                 AND entrega_empenhada IS NOT NULL
                 AND entrega_empenhada < CURRENT_DATE
                 AND (entrega_prorrogada IS NULL OR entrega_prorrogada < CURRENT_DATE)
                THEN 'VENCIDO'
                WHEN status = 'ANDAMENTO'
                 AND COALESCE(entrega_prorrogada, entrega_empenhada) IS NOT NULL
                 AND COALESCE(entrega_prorrogada, entrega_empenhada) <= CURRENT_DATE + INTERVAL '7 days'
                THEN 'PROXIMO'
                ELSE NULL
            END AS alerta
        {base}
        ORDER BY ano DESC, numero
        LIMIT {limit} OFFSET {offset}
    """), params).mappings().all()

    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}


@router.get("/minhas-pendencias")
def minhas_pendencias(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna processos com pendência ativa onde o usuário logado é o responsável.
    Critério: o campo pendencia do processo contém o apelido_assinatura do usuário (ILIKE).
    Exclui processos onde o usuário já deu baixa."""
    apelido = (current_user.apelido_assinatura or "").strip()
    if not apelido:
        return {"total": 0, "pendencias": []}

    rows = db.execute(text("""
        SELECT
            p.id, p.numero, p.processo_sei, p.processo_siafem,
            p.licitacao, p.solicitante, p.objeto,
            p.valor_empenhado, p.responsavel, p.pendencia,
            COALESCE(p.entrega_prorrogada, p.entrega_empenhada) AS prazo,
            CASE
                WHEN COALESCE(p.entrega_prorrogada, p.entrega_empenhada) < CURRENT_DATE
                    THEN 'VENCIDO'
                WHEN COALESCE(p.entrega_prorrogada, p.entrega_empenhada) <= CURRENT_DATE + INTERVAL '5 days'
                    THEN 'URGENTE'
                ELSE NULL
            END AS alerta
        FROM uge.processos p
        WHERE p.pendencia IS NOT NULL
          AND p.pendencia ILIKE '%' || :apelido || '%'
          AND p.status != 'CANCELADO'
          AND NOT EXISTS (
              SELECT 1 FROM uge.pendencia_baixas b
              WHERE b.processo_id   = p.id
                AND b.usuario_id    = :uid
                AND b.pendencia_texto = p.pendencia
          )
        ORDER BY
            CASE WHEN COALESCE(p.entrega_prorrogada, p.entrega_empenhada) < CURRENT_DATE THEN 0 ELSE 1 END,
            COALESCE(p.entrega_prorrogada, p.entrega_empenhada) NULLS LAST,
            p.numero
    """), {"apelido": apelido, "uid": current_user.id}).mappings().all()

    return {"total": len(rows), "pendencias": [dict(r) for r in rows]}


class BaixaRequest(BaseModel):
    processo_id: int


@router.post("/pendencias/baixar")
def baixar_pendencia(
    req: BaixaRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Registra a baixa de uma pendência pelo usuário logado."""
    proc = db.execute(text("""
        SELECT id, pendencia FROM uge.processos WHERE id = :id
    """), {"id": req.processo_id}).mappings().first()
    if not proc:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    apelido = (current_user.apelido_assinatura or "").strip()
    if not apelido or apelido.lower() not in (proc["pendencia"] or "").lower():
        raise HTTPException(status_code=403, detail="Esta pendência não é sua")

    try:
        db.execute(text("""
            INSERT INTO uge.pendencia_baixas (processo_id, usuario_id, pendencia_texto)
            VALUES (:pid, :uid, :texto)
            ON CONFLICT DO NOTHING
        """), {"pid": req.processo_id, "uid": current_user.id, "texto": proc["pendencia"]})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "processo_id": req.processo_id, "assinado_por": current_user.nome}


@router.get("/filtros")
def filtros_uge(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    licitacoes   = [r[0] for r in db.execute(text("SELECT DISTINCT licitacao FROM uge.processos WHERE licitacao IS NOT NULL ORDER BY licitacao")).fetchall()]
    solicitantes = [r[0] for r in db.execute(text("SELECT DISTINCT solicitante FROM uge.processos WHERE solicitante IS NOT NULL ORDER BY solicitante")).fetchall()]
    responsaveis = [r[0] for r in db.execute(text("SELECT DISTINCT responsavel FROM uge.processos WHERE responsavel IS NOT NULL ORDER BY responsavel")).fetchall()]
    statuses     = [r[0] for r in db.execute(text("SELECT DISTINCT status FROM uge.processos WHERE status IS NOT NULL ORDER BY status")).fetchall()]
    return {
        "licitacoes":   licitacoes,
        "solicitantes": solicitantes,
        "responsaveis": responsaveis,
        "statuses":     statuses,
    }
