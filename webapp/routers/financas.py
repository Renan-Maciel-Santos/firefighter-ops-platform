"""
Finanças — quanto cada SGB custa por mês e por ano.

Substitui a planilha "Gastos das prefeituras por SGB": cada SGB lança, por
posto/município e por mês, o que a prefeitura gastou em sete categorias. Os
recursos geridos pela UGE (TAC, emendas, FUNDABOM...) entram à parte e somam
no total geral do 11º GB.

Duas abas no painel, com permissão separada (webapp/acesso.py):
    fin_indicadores  só leitura — comparativo entre SGBs
    fin_lancamento   formulário — grava em financas.gastos e recursos_uge

Schema: Financas/create_financas.sql.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user

router = APIRouter(prefix="/financas", tags=["financas"])

SGBS = ("1°SGB", "2°SGB", "3°SGB", "4°SGB")
# Ordem e rótulo iguais aos da planilha, que é o que os SGBs conhecem.
CATEGORIAS = (
    ("tel", "Telefone"),
    ("agua", "Água"),
    ("energia", "Energia"),
    ("combustivel", "Combustível"),
    ("manutencao_frota", "Manutenção de frota"),
    ("alimentacao", "Alimentação"),
    ("outros", "Outros"),
)
CHAVES_CAT = tuple(c for c, _ in CATEGORIAS)
# Lista fechada pedida pelo Cmt (09/11/2026). Mesma lista no CHECK do banco.
FONTES_UGE = ("RINEM", "Tesouro", "Emenda Parlamentar", "TAC", "Prestação Pecuniária", "FEPOM", "Doação")


def exigir_aba(user: Usuario, *abas: str):
    if not any(pode_ver(user, a) for a in abas):
        raise HTTPException(status_code=403, detail="Acesso negado")


def ler(user):   exigir_aba(user, "fin_indicadores", "fin_lancamento")
def gravar(user): exigir_aba(user, "fin_lancamento")


def _f(v):
    return float(v) if v is not None else None


# ------------------------------------------------------------------ estrutura
@router.get("/estrutura")
def estrutura(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    ler(current_user)
    locais = db.execute(text("""
        SELECT id, sgb, nome, observacao FROM financas.locais
        WHERE ativo ORDER BY sgb, ordem, nome
    """)).mappings().all()
    anos = [r[0] for r in db.execute(text("""
        SELECT DISTINCT ano FROM financas.gastos
        UNION SELECT DISTINCT ano FROM financas.recursos_uge ORDER BY 1 DESC
    """)).fetchall()]
    return {
        "sgbs": SGBS,
        "categorias": [{"chave": c, "rotulo": r} for c, r in CATEGORIAS],
        "locais": [dict(r) for r in locais],
        "anos": anos,
        "fontes_uge": FONTES_UGE,
    }


# ---------------------------------------------------------------- lançamento
@router.get("/lancamentos")
def lancamentos(
    ano: int = Query(...), sgb: str = Query(...), mes: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user),
):
    """Valores de um SGB num mês — uma linha por local × categoria já lançada."""
    ler(current_user)
    linhas = db.execute(text("""
        SELECT g.local_id, g.categoria, g.valor, g.atualizado_por, g.atualizado_em
        FROM financas.gastos g JOIN financas.locais l ON l.id = g.local_id
        WHERE g.ano = :ano AND g.mes = :mes AND l.sgb = :sgb
    """), {"ano": ano, "mes": mes, "sgb": sgb}).mappings().all()
    return {"itens": [{**dict(r), "valor": _f(r["valor"])} for r in linhas]}


class ItemGasto(BaseModel):
    local_id: int
    categoria: str
    # None apaga o valor (célula em branco).
    valor: Optional[float] = Field(None, ge=0, le=100_000_000)


class LoteGastos(BaseModel):
    ano: int = Field(..., ge=2020, le=2100)
    mes: int = Field(..., ge=1, le=12)
    itens: list[ItemGasto]


@router.put("/lancamentos")
def salvar_lancamentos(lote: LoteGastos, db: Session = Depends(get_db),
                       current_user: Usuario = Depends(get_current_user)):
    gravar(current_user)
    validos = {r[0] for r in db.execute(text("SELECT id FROM financas.locais WHERE ativo")).fetchall()}
    gravados = apagados = 0
    for it in lote.itens:
        if it.local_id not in validos or it.categoria not in CHAVES_CAT:
            raise HTTPException(400, f"Local {it.local_id} / categoria {it.categoria!r} inválidos")
        chave = {"ano": lote.ano, "mes": lote.mes, "local_id": it.local_id, "categoria": it.categoria}
        if it.valor is None:
            apagados += db.execute(text("""
                DELETE FROM financas.gastos
                WHERE ano = :ano AND mes = :mes AND local_id = :local_id AND categoria = :categoria
            """), chave).rowcount
            continue
        db.execute(text("""
            INSERT INTO financas.gastos (ano, mes, local_id, categoria, valor, atualizado_por)
            VALUES (:ano, :mes, :local_id, :categoria, :valor, :por)
            ON CONFLICT (ano, mes, local_id, categoria) DO UPDATE
               SET valor = EXCLUDED.valor,
                   atualizado_por = EXCLUDED.atualizado_por, atualizado_em = NOW()
        """), {**chave, "valor": round(it.valor, 2), "por": current_user.nome})
        gravados += 1
    db.commit()
    return {"gravados": gravados, "apagados": apagados}


# --------------------------------------------------------------- recursos UGE
@router.get("/recursos-uge")
def recursos_uge(ano: int = Query(...), db: Session = Depends(get_db),
                 current_user: Usuario = Depends(get_current_user)):
    ler(current_user)
    linhas = db.execute(text("""
        SELECT id, descricao, valor, fonte, atualizado_por, atualizado_em
        FROM financas.recursos_uge WHERE ano = :ano ORDER BY ordem, id
    """), {"ano": ano}).mappings().all()
    return {"itens": [{**dict(r), "valor": _f(r["valor"])} for r in linhas]}


class RecursoUge(BaseModel):
    id: Optional[int] = None
    descricao: str = Field(..., min_length=1, max_length=200)
    valor: float = Field(..., ge=0, le=1_000_000_000)
    fonte: str


class LoteRecursos(BaseModel):
    ano: int = Field(..., ge=2020, le=2100)
    itens: list[RecursoUge]


@router.put("/recursos-uge")
def salvar_recursos_uge(lote: LoteRecursos, db: Session = Depends(get_db),
                        current_user: Usuario = Depends(get_current_user)):
    """Substitui a lista do ano pela enviada: o que saiu da lista é apagado."""
    gravar(current_user)
    for it in lote.itens:
        if it.fonte not in FONTES_UGE:
            raise HTTPException(400, f"Fonte pagadora inválida: {it.fonte!r}")
    manter = [it.id for it in lote.itens if it.id]
    db.execute(text("""
        DELETE FROM financas.recursos_uge
        WHERE ano = :ano AND NOT (id = ANY(:manter))
    """), {"ano": lote.ano, "manter": manter})
    for ordem, it in enumerate(lote.itens, start=1):
        p = {"ano": lote.ano, "descricao": it.descricao.strip(), "valor": round(it.valor, 2),
             "fonte": it.fonte, "ordem": ordem, "por": current_user.nome}
        if it.id:
            db.execute(text("""
                UPDATE financas.recursos_uge
                   SET descricao = :descricao, valor = :valor, fonte = :fonte, ordem = :ordem,
                       atualizado_por = :por, atualizado_em = NOW()
                 WHERE id = :id AND ano = :ano
            """), {**p, "id": it.id})
        else:
            db.execute(text("""
                INSERT INTO financas.recursos_uge (ano, descricao, valor, fonte, ordem, atualizado_por)
                VALUES (:ano, :descricao, :valor, :fonte, :ordem, :por)
            """), p)
    db.commit()
    return {"itens": len(lote.itens)}


# ---------------------------------------------------------------- indicadores
@router.get("/indicadores")
def indicadores(ano: int = Query(...), db: Session = Depends(get_db),
                current_user: Usuario = Depends(get_current_user)):
    ler(current_user)
    p = {"ano": ano}

    mensal = db.execute(text("""
        SELECT l.sgb, g.mes, COALESCE(SUM(g.valor), 0) AS total
        FROM financas.gastos g JOIN financas.locais l ON l.id = g.local_id
        WHERE g.ano = :ano GROUP BY l.sgb, g.mes
    """), p).mappings().all()
    por_sgb_mes = {s: [0.0] * 12 for s in SGBS}
    for r in mensal:
        por_sgb_mes[r["sgb"]][r["mes"] - 1] = float(r["total"])

    cat = db.execute(text("""
        SELECT l.sgb, g.categoria, COALESCE(SUM(g.valor), 0) AS total
        FROM financas.gastos g JOIN financas.locais l ON l.id = g.local_id
        WHERE g.ano = :ano GROUP BY l.sgb, g.categoria
    """), p).mappings().all()
    por_sgb_cat = {s: {c: 0.0 for c in CHAVES_CAT} for s in SGBS}
    for r in cat:
        por_sgb_cat[r["sgb"]][r["categoria"]] = float(r["total"])

    locais = db.execute(text("""
        SELECT l.id, l.sgb, l.nome, COALESCE(SUM(g.valor), 0) AS total,
               COUNT(DISTINCT g.mes) AS meses
        FROM financas.locais l
        LEFT JOIN financas.gastos g ON g.local_id = l.id AND g.ano = :ano
        WHERE l.ativo GROUP BY l.id ORDER BY total DESC
    """), p).mappings().all()

    # Preenchimento: % dos postos do SGB com pelo menos um valor no mês. Por
    # posto, não por célula: célula em branco é normal (despesa que a
    # prefeitura não paga), posto inteiro em branco é mês não lançado.
    preench = db.execute(text("""
        SELECT l.sgb, m.mes,
               COUNT(DISTINCT g.local_id) AS lancadas,
               COUNT(DISTINCT l.id) AS esperadas
        FROM financas.locais l
        CROSS JOIN generate_series(1, 12) AS m(mes)
        LEFT JOIN financas.gastos g ON g.local_id = l.id AND g.ano = :ano AND g.mes = m.mes
        WHERE l.ativo GROUP BY l.sgb, m.mes
    """), p).mappings().all()
    preenchimento = {s: [0.0] * 12 for s in SGBS}
    for r in preench:
        if r["esperadas"]:
            preenchimento[r["sgb"]][r["mes"] - 1] = round(100 * r["lancadas"] / r["esperadas"], 1)

    uge = db.execute(text("""
        SELECT COALESCE(SUM(valor), 0) FROM financas.recursos_uge WHERE ano = :ano
    """), p).scalar()
    uge_fonte = {f: 0.0 for f in FONTES_UGE}
    for f, v in db.execute(text("""
        SELECT fonte, SUM(valor) FROM financas.recursos_uge WHERE ano = :ano GROUP BY fonte
    """), p).fetchall():
        uge_fonte[f or "Sem fonte"] = float(v)

    return {
        "ano": ano,
        "sgbs": SGBS,
        "categorias": [{"chave": c, "rotulo": r} for c, r in CATEGORIAS],
        "por_sgb_mes": por_sgb_mes,
        "por_sgb_categoria": por_sgb_cat,
        "por_local": [{**dict(r), "total": float(r["total"])} for r in locais],
        "preenchimento": preenchimento,
        "total_prefeituras": round(sum(sum(v) for v in por_sgb_mes.values()), 2),
        "total_uge": float(uge or 0),
        "uge_por_fonte": uge_fonte,
    }
