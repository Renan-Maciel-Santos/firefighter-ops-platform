"""
Afastamentos do efetivo — página própria no B/1 (11/11/2026).

Antes ficava como uma tabela no fim da aba Pessoal. O Comando pediu a % do
efetivo afastado no mês por SGB e por seção, e quem está afastado no dia.

A % segue a régua padronizada para a B.I.A. no mesmo dia (/consulta/ferias):
o MAIOR número de militares afastados no MESMO DIA dentro do mês, sobre o
efetivo. Contar quem tem qualquer dia de afastamento no mês não serve: com as
férias em dois períodos de 15 dias, cada militar aparece em 2-3 meses e todo
mês passa de 16% sem que haja concentração nenhuma.

Fonte: b1.v_afastamentos_dedup (só o que ainda está no SGP). Ficam fora a
licença-prêmio em pecúnia e o que está sobrestado — não tiram ninguém do
serviço. O efetivo é o atual (b1.efetivo ativo), classificado por
efetivo_regras.SQL_PARTE; a seção é a OPM atual do militar.
"""
import calendar
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from efetivo_regras import SQL_PARTE, PARTES_EM
from routers.auth import get_current_user

router = APIRouter(prefix="/afastamentos", tags=["afastamentos"])

ABA = "afastamentos"

ORDEM_PARTES = ("1°Sgb", "2°Sgb", "3°Sgb", "4°Sgb") + PARTES_EM + ("Outros",)

# Grupos do filtro da tela -> motivos do SGP (motivo_grupo da view).
GRUPOS_MOTIVO = {
    "ferias":   ("FERIAS",),
    "lp":       ("LICENCA-PREMIO",),
    "dispensa": ("DISPENSA DO SERVICO", "DISPENSA RECOMPENSA"),
    "saude":    ("CONVALESCENCA", "LICENÇA TRAT. SAÚDE"),
}
ROTULO_GRUPO = {"ferias": "Férias", "lp": "Licença-prêmio", "dispensa": "Dispensas",
                "saude": "Saúde", "outros": "Outros"}

_FORA = "motivo_grupo NOT ILIKE '%PECUNIA%' AND motivo_grupo NOT ILIKE '%SOBREST%'"


def check_access(user: Usuario):
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


def _filtro_motivo(grupo: Optional[str], params: dict) -> str:
    if not grupo or grupo == "todos":
        return ""
    if grupo == "outros":
        todos = [m for ms in GRUPOS_MOTIVO.values() for m in ms]
        params["motivos_fora"] = todos
        return " AND NOT (motivo_grupo = ANY(:motivos_fora))"
    if grupo not in GRUPOS_MOTIVO:
        raise HTTPException(status_code=400, detail=f"Motivo desconhecido: {grupo}")
    params["motivos"] = list(GRUPOS_MOTIVO[grupo])
    return " AND motivo_grupo = ANY(:motivos)"


def _grupo_de(motivo: str) -> str:
    for g, ms in GRUPOS_MOTIVO.items():
        if motivo in ms:
            return g
    return "outros"


def _efetivo(db: Session):
    """Efetivo atual por lotação e por (lotação, seção)."""
    rows = db.execute(text(f"""
        SELECT {SQL_PARTE} AS parte, opm_atual AS secao, COUNT(*) AS n
          FROM b1.efetivo WHERE ativo = true GROUP BY 1, 2
    """)).mappings().all()
    por_parte, por_secao = {}, {}
    for r in rows:
        por_parte[r["parte"]] = por_parte.get(r["parte"], 0) + r["n"]
        por_secao[(r["parte"], r["secao"])] = r["n"]
    return por_parte, por_secao


def _afastados_por_dia(db: Session, ini: date, fim: date, motivo: Optional[str]):
    """(dia, parte, seção, re) de quem está afastado em cada dia do intervalo."""
    params = {"ini": ini, "fim": fim}
    filtro = _filtro_motivo(motivo, params)
    return db.execute(text(f"""
        WITH a AS (
            SELECT DISTINCT re, data_inicio, COALESCE(data_fim, data_inicio) AS data_fim
              FROM b1.v_afastamentos_dedup
             WHERE {_FORA} {filtro}
               AND data_inicio <= :fim AND COALESCE(data_fim, data_inicio) >= :ini
        ), e AS (
            SELECT re, {SQL_PARTE} AS parte, opm_atual AS secao FROM b1.efetivo WHERE ativo = true
        )
        SELECT DISTINCT d::date AS dia, e.parte, e.secao, e.re
          FROM a
          JOIN e ON e.re = a.re
          CROSS JOIN LATERAL generate_series(GREATEST(a.data_inicio, :ini), LEAST(a.data_fim, :fim),
                                             interval '1 day') AS d
    """), params).mappings().all()


def _pct(n, tot):
    return round(100 * n / tot, 1) if tot else None


@router.get("/motivos")
def motivos(current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    return [{"id": "todos", "rotulo": "Todos os motivos"}] + [
        {"id": g, "rotulo": ROTULO_GRUPO[g]} for g in ("ferias", "lp", "dispensa", "saude", "outros")]


@router.get("/anual")
def anual(
    ano: Optional[int] = Query(None),
    motivo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """% do efetivo afastado em cada mês (pico no mesmo dia), por lotação."""
    check_access(current_user)
    ano = ano or date.today().year
    ef_parte, _ = _efetivo(db)
    linhas = _afastados_por_dia(db, date(ano, 1, 1), date(ano, 12, 31), motivo)

    # (parte, dia) -> nº de militares; o total soma todas as partes.
    por_dia = {}
    for r in linhas:
        for p in (r["parte"], "TOTAL"):
            por_dia.setdefault((p, r["dia"]), set()).add(r["re"])

    ef_parte = {**ef_parte, "TOTAL": sum(ef_parte.values())}
    out = []
    for parte in [p for p in ORDEM_PARTES if p in ef_parte] + ["TOTAL"]:
        meses = []
        for mm in range(1, 13):
            dias = range(1, calendar.monthrange(ano, mm)[1] + 1)
            pico = max(len(por_dia.get((parte, date(ano, mm, d)), ())) for d in dias)
            meses.append({"mes": mm, "pico": pico, "pct": _pct(pico, ef_parte[parte])})
        out.append({"lotacao": parte, "efetivo": ef_parte[parte], "meses": meses})
    return {"ano": ano, "linhas": out}


@router.get("/mes")
def mes(
    ano: Optional[int] = Query(None),
    mes: Optional[int] = Query(None, ge=1, le=12),
    motivo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """O mês por lotação e seção: pico no mesmo dia, % do efetivo e quantos
    tiveram algum afastamento no mês."""
    check_access(current_user)
    hoje = date.today()
    ano, mes = ano or hoje.year, mes or hoje.month
    ini, fim = date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])
    ef_parte, ef_secao = _efetivo(db)
    linhas = _afastados_por_dia(db, ini, fim, motivo)

    dia_parte, dia_secao, no_mes_parte, no_mes_secao = {}, {}, {}, {}
    for r in linhas:
        dia_parte.setdefault((r["parte"], r["dia"]), set()).add(r["re"])
        dia_secao.setdefault((r["parte"], r["secao"], r["dia"]), set()).add(r["re"])
        no_mes_parte.setdefault(r["parte"], set()).add(r["re"])
        no_mes_secao.setdefault((r["parte"], r["secao"]), set()).add(r["re"])
    dias = [date(ano, mes, d) for d in range(1, fim.day + 1)]

    def pico(chave_dia):
        return max(len(chave_dia(d)) for d in dias)

    out = []
    for parte in [p for p in ORDEM_PARTES if p in ef_parte]:
        secoes = []
        for (pt, sec), n in sorted(ef_secao.items(), key=lambda kv: str(kv[0][1])):
            if pt != parte:
                continue
            pk = pico(lambda d: dia_secao.get((pt, sec, d), ()))
            secoes.append({"secao": sec, "efetivo": n, "pico": pk, "pct": _pct(pk, n),
                           "no_mes": len(no_mes_secao.get((pt, sec), ()))})
        pk = pico(lambda d: dia_parte.get((parte, d), ()))
        out.append({"lotacao": parte, "efetivo": ef_parte[parte], "pico": pk,
                    "pct": _pct(pk, ef_parte[parte]), "no_mes": len(no_mes_parte.get(parte, ())),
                    "secoes": secoes})
    total_ef = sum(ef_parte.values())
    pk_total = max(len({r for (p, d), rs in dia_parte.items() if d == dia for r in rs}) for dia in dias)
    return {"ano": ano, "mes": mes, "lotacoes": out,
            "total": {"efetivo": total_ef, "pico": pk_total, "pct": _pct(pk_total, total_ef),
                      "no_mes": len({r["re"] for r in linhas})}}


@router.get("/dia")
def dia(
    data: Optional[date] = Query(None),
    motivo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Quem está afastado no dia, com motivo e período."""
    check_access(current_user)
    data = data or date.today()
    params = {"dia": data}
    filtro = _filtro_motivo(motivo, params)
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (e.re, a.motivo_grupo, a.data_inicio)
               e.re, e.posto_grad, e.nome, {SQL_PARTE.replace('cod_opm_atual', 'e.cod_opm_atual')} AS lotacao,
               e.opm_atual AS secao, a.motivo_grupo AS motivo, a.data_inicio, a.data_fim, a.quantidade_dias
          FROM b1.v_afastamentos_dedup a
          JOIN b1.efetivo e ON e.re = a.re AND e.ativo = true
         WHERE {_FORA.replace('motivo_grupo', 'a.motivo_grupo')} {filtro.replace('motivo_grupo', 'a.motivo_grupo')}
           AND a.data_inicio <= :dia AND COALESCE(a.data_fim, a.data_inicio) >= :dia
    """), params).mappings().all()
    ordem = {p: i for i, p in enumerate(ORDEM_PARTES)}
    lista = sorted((dict(r) for r in rows), key=lambda r: (ordem.get(r["lotacao"], 99), r["secao"] or "", r["nome"]))
    for r in lista:
        r["grupo"] = _grupo_de(r["motivo"])
    efetivo = db.execute(text("SELECT COUNT(*) FROM b1.efetivo WHERE ativo = true")).scalar() or 0
    militares = len({r["re"] for r in lista})
    return {"data": data, "total": militares, "efetivo": efetivo, "pct": _pct(militares, efetivo),
            "por_grupo": {ROTULO_GRUPO[g]: len({r["re"] for r in lista if r["grupo"] == g})
                          for g in ROTULO_GRUPO if any(r["grupo"] == g for r in lista)},
            "lista": lista}
