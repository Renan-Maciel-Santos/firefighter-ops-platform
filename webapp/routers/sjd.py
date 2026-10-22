"""
Rotas /sjd/* — Serviço de Justiça e Disciplina.

Consome sjd.processos e sjd.indicadores_mensais (populados pelo ETL sjd_etl.py).
Acesso: perfis 'comando' e 'administrativo'.
"""

from typing import Optional
from datetime import date
from calendar import monthrange

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user


router = APIRouter(prefix="/sjd", tags=["sjd"])

ABA = "sjd"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


PUNICOES_EFETIVAS = {
    "REPREENSÃO", "REPREENSAO",
    "PERMANÊNCIA", "PERMANENCIA",       # sanção disciplinar RDPM Art. 14
    "DETENÇÃO", "DETENCAO",
    "PRISÃO", "PRISAO", "IMPEDIMENTO",
    "LICENCIAMENTO A BEM DA DISCIPLINA",
    "EXCLUSÃO", "EXCLUSAO", "DEMISSÃO", "DEMISSAO",
    "REFORMA COMPULSÓRIA", "REFORMA COMPULSORIA",
}


def _norm_upper(s):
    if not s: return ""
    return str(s).strip().upper() \
        .replace("Ç", "C").replace("Ã", "A").replace("Õ", "O") \
        .replace("Á", "A").replace("É", "E").replace("Í", "I") \
        .replace("Ó", "O").replace("Ú", "U")


def _periodo(ano: Optional[int], semestre: Optional[int]):
    """Retorna (data_inicio, data_fim, meses[]). Defaults: ano corrente inteiro."""
    ano = ano or date.today().year
    if semestre in (1, 2):
        mi = 1 if semestre == 1 else 7
        mf = 6 if semestre == 1 else 12
    else:
        mi, mf = 1, 12
    return (date(ano, mi, 1),
            date(ano, mf, monthrange(ano, mf)[1]),
            list(range(mi, mf + 1)),
            ano)


# --------------------------------------------------------------------
# RESUMO — 4 KPIs + totais por tipo + punições
# --------------------------------------------------------------------
@router.get("/resumo")
def resumo(
    ano: Optional[int] = Query(None),
    semestre: Optional[int] = Query(None, ge=1, le=2),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    dini, dfim, meses, ano = _periodo(ano, semestre)

    # 4 KPIs consolidados (os mesmos que aparecem no relatório PPTX)
    agreg = db.execute(text("""
        SELECT indicador, SUM(valor) AS total
        FROM sjd.indicadores_mensais
        WHERE ano = :ano AND mes = ANY(:meses)
        GROUP BY indicador
    """), {"ano": ano, "meses": meses}).all()
    ind = {r[0]: int(r[1]) for r in agreg}

    # PDs com decisão de pena efetiva (conta EVENTOS — 1 militar punido 2× em datas
    # distintas soma 2, é essa a métrica de comando)
    pd_rows = db.execute(text("""
        SELECT punicao FROM sjd.processos
        WHERE tipo='PD' AND data_abertura BETWEEN :ini AND :fim AND punicao IS NOT NULL
    """), {"ini": dini, "fim": dfim}).all()
    pms_punidos = sum(1 for r in pd_rows if _norm_upper(r[0]) in PUNICOES_EFETIVAS)

    # Total por tipo no período
    por_tipo = db.execute(text("""
        SELECT COALESCE(tipo, '(não informado)') AS tipo, COUNT(*) AS qtd
        FROM sjd.processos
        WHERE data_abertura BETWEEN :ini AND :fim
        GROUP BY tipo ORDER BY qtd DESC
    """), {"ini": dini, "fim": dfim}).mappings().all()

    # Status (finalizado/andamento)
    por_status = db.execute(text("""
        SELECT COALESCE(finalizado, '(vazio)') AS finalizado, COUNT(*) AS qtd
        FROM sjd.processos
        WHERE data_abertura BETWEEN :ini AND :fim
        GROUP BY finalizado ORDER BY qtd DESC
    """), {"ini": dini, "fim": dfim}).mappings().all()

    # Distribuição de punições nos PDs
    pd_por_punicao = db.execute(text("""
        SELECT COALESCE(punicao, '(em andamento)') AS punicao, COUNT(*) AS qtd
        FROM sjd.processos
        WHERE tipo='PD' AND data_abertura BETWEEN :ini AND :fim
        GROUP BY punicao ORDER BY qtd DESC
    """), {"ini": dini, "fim": dfim}).mappings().all()

    # Última carga (frescor do dado)
    last = db.execute(text("""
        SELECT MAX(atualizado_em) FROM sjd.processos
    """)).scalar()

    return {
        "periodo": {"ano": ano, "semestre": semestre,
                    "inicio": dini.isoformat(), "fim": dfim.isoformat()},
        "kpis": {
            "acidentes_folga_bombeiro": ind.get("acidentes_folga_bombeiro", 0),
            "acidentes_viatura_vitima": ind.get("acidentes_viatura_vitima", 0),
            "reclamacoes_denuncias":    ind.get("reclamacoes_denuncias", 0),
            "pms_punidos_pd":           pms_punidos,
            "total_processos":          sum(r["qtd"] for r in por_tipo),
        },
        "por_tipo":       [dict(r) for r in por_tipo],
        "por_status":     [dict(r) for r in por_status],
        "pd_por_punicao": [dict(r) for r in pd_por_punicao],
        "atualizado_em":  last.isoformat() if last else None,
    }


# --------------------------------------------------------------------
# INDICADORES MENSAIS — série temporal pra montar gráfico
# --------------------------------------------------------------------
@router.get("/indicadores-mensais")
def indicadores_mensais(
    ano: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    ano = ano or date.today().year
    rows = db.execute(text("""
        SELECT indicador, mes, valor FROM sjd.indicadores_mensais
        WHERE ano = :ano ORDER BY indicador, mes
    """), {"ano": ano}).all()

    resultado = {}
    for indicador, mes, valor in rows:
        resultado.setdefault(indicador, [0]*12)
        resultado[indicador][mes-1] = int(valor)
    return {"ano": ano, "series": resultado}


# --------------------------------------------------------------------
# PROCESSOS — lista com filtros e paginação
# --------------------------------------------------------------------
@router.get("/processos")
def processos(
    ano: Optional[int] = Query(None),
    semestre: Optional[int] = Query(None, ge=1, le=2),
    tipo: Optional[str] = Query(None),
    unidade: Optional[str] = Query(None),
    finalizado: Optional[str] = Query(None),
    busca: Optional[str] = Query(None, description="Busca em titulo/interessado"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    dini, dfim, _, _ = _periodo(ano, semestre)

    filtros = ["data_abertura BETWEEN :ini AND :fim"]
    params  = {"ini": dini, "fim": dfim}
    if tipo:
        filtros.append("tipo = :tipo"); params["tipo"] = tipo
    if unidade:
        filtros.append("unidade = :unidade"); params["unidade"] = unidade
    if finalizado:
        filtros.append("finalizado = :fin"); params["fin"] = finalizado
    if busca:
        filtros.append("(titulo ILIKE :q OR interessado ILIKE :q)")
        params["q"] = f"%{busca}%"

    where = " AND ".join(filtros)
    total = db.execute(text(f"SELECT COUNT(*) FROM sjd.processos WHERE {where}"),
                       params).scalar()

    params["limit"] = limit
    params["offset"] = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT id, data_abertura, titulo, tipo, interessado,
               unidade, punicao, finalizado
        FROM sjd.processos
        WHERE {where}
        ORDER BY data_abertura DESC, id DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {
        "total": total, "page": page, "limit": limit,
        "data": [dict(r) for r in rows],
    }


# --------------------------------------------------------------------
# FILTROS — opções pros dropdowns da UI
# --------------------------------------------------------------------
@router.get("/filtros")
def filtros(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    tipos = [r[0] for r in db.execute(text("""
        SELECT DISTINCT tipo FROM sjd.processos
        WHERE tipo IS NOT NULL ORDER BY tipo
    """)).all()]
    unidades = [r[0] for r in db.execute(text("""
        SELECT DISTINCT unidade FROM sjd.processos
        WHERE unidade IS NOT NULL ORDER BY unidade
    """)).all()]
    situacoes = [r[0] for r in db.execute(text("""
        SELECT DISTINCT finalizado FROM sjd.processos
        WHERE finalizado IS NOT NULL ORDER BY finalizado
    """)).all()]
    anos = [int(r[0]) for r in db.execute(text("""
        SELECT DISTINCT EXTRACT(YEAR FROM data_abertura)::INT AS ano
        FROM sjd.processos ORDER BY ano DESC
    """)).all()]
    return {"tipos": tipos, "unidades": unidades,
            "situacoes": situacoes, "anos": anos}
