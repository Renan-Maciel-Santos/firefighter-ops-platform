from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from efetivo_regras import (SQL_PARTE, SQL_OPERACIONAL, PARTES_EM,
                            SQL_PARTE_QPO, SQL_VAGA_OPERACIONAL)
from routers.auth import get_current_user

router = APIRouter(prefix="/pessoal", tags=["pessoal"])

ABA = "pessoal"


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/resumo")
def resumo_pessoal(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    row = db.execute(text("SELECT * FROM b1.vw_qpo_resumo_geral")).mappings().first()
    return dict(row) if row else {}


@router.get("/qpo-lotacao")
def qpo_por_lotacao(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    rows = db.execute(text("SELECT * FROM b1.vw_qpo_resumo_lotacao ORDER BY lotacao")).mappings().all()
    return [dict(r) for r in rows]


# Quebra do EM em três linhas no painel. "EM + COBOM" numa linha só escondia
# realidades opostas: o COBOM tem 30 militares e é 100% operacional, enquanto o
# resto do EM é administrativo e puxava o percentual para 45% — número que não
# descreve nem um nem outro. Ver B1/QPO_11GB.xls, aba 11GB.
#
# Quem é SAT, COBOM, ADM ou SGB, e quem é operacional, vem de efetivo_regras.py
# — a SAT inclui os NATs dos SGBs desde 11/09/2026.

# Vagas do QPO para cada pedaço do EM. COBOM e Seção Ativ Téc só existem
# separados porque b1.qpo_funcoes guarda o QPO por seção; b1.qpo_vagas tem o EM
# como uma linha de 81. O ADM é o resto, calculado, para os três sempre fecharem
# com as 81 do agregado mesmo que o QPO mude.
SQL_VAGAS_EM = """
    SELECT
        COALESCE(SUM(vagas) FILTER (WHERE NOT a_designar
                                      AND subsecao ILIKE '%%COBOM%%'), 0)   AS cobom,
        COALESCE(SUM(vagas) FILTER (WHERE NOT a_designar
                                      AND secao ILIKE '%%Ativ T%%'), 0)     AS sat,
        COALESCE(SUM(vagas) FILTER (WHERE NOT a_designar), 0)               AS total
      FROM b1.qpo_funcoes
     WHERE lotacao = 'EM'
"""


@router.get("/operacional")
def efetivo_operacional(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)

    # Direto de b1.efetivo, não da b1.vw_efetivo_operacional. A view classifica
    # por prefixo de 6 dígitos: põe os NATs (99011x900) nos SGBs, como não
    # operacionais, e não conhece o override da SAT — o endpoint remendava só a
    # sede 990119200 e a SAT saía com 12 ativos e 6 operacionais em vez de 20 e
    # 13. A view fica como está porque também alimenta o PPQG.
    partes = {
        r["parte"]: dict(r)
        for r in db.execute(text(f"""
            SELECT {SQL_PARTE}                                   AS parte,
                   COUNT(*)                                      AS total_ativos,
                   COUNT(*) FILTER (WHERE {SQL_OPERACIONAL})     AS total_operacional
              FROM b1.efetivo
             WHERE ativo = true
             GROUP BY 1
        """)).mappings().all()
    }

    v = db.execute(text(SQL_VAGAS_EM)).mappings().first() or {}
    vagas_em = {
        "COBOM": int(v.get("cobom") or 0),
        "SAT":   int(v.get("sat") or 0),
        "ADM":   int(v.get("total") or 0) - int(v.get("cobom") or 0) - int(v.get("sat") or 0),
    }

    vagas_lotacao = {
        r["lotacao"]: int(r["vagas"])
        for r in db.execute(text(
            "SELECT lotacao, SUM(vagas) AS vagas FROM b1.qpo_vagas GROUP BY lotacao"
        )).mappings().all()
    }
    vagas_lotacao["TOTAL GERAL"] = sum(vagas_lotacao.values())

    def linha(rotulo, total, operacional, vagas):
        return {
            "lotacao": rotulo,
            "total_ativos": total,
            "total_operacional": operacional,
            "perc_operacional": round(100 * operacional / total, 1) if total else 0,
            "vagas": vagas,
        }

    # Mesma ordem que a view dava: SGBs, as três partes do EM, Outros só se
    # houver alguém fora da árvore do 11º GB, e o total.
    vazio = {"total_ativos": 0, "total_operacional": 0}
    out = []
    for sgb in ("1°Sgb", "2°Sgb", "3°Sgb", "4°Sgb"):
        p = partes.get(sgb, vazio)
        out.append(linha(sgb, p["total_ativos"], p["total_operacional"], vagas_lotacao.get(sgb)))
    for parte in PARTES_EM:
        p = partes.get(parte, vazio)
        out.append(linha(parte, p["total_ativos"], p["total_operacional"], vagas_em[parte]))
    if "Outros" in partes:
        p = partes["Outros"]
        out.append(linha("Outros", p["total_ativos"], p["total_operacional"], None))

    out.append(linha(
        "TOTAL GERAL",
        sum(p["total_ativos"] for p in partes.values()),
        sum(p["total_operacional"] for p in partes.values()),
        vagas_lotacao["TOTAL GERAL"],
    ))
    return out


@router.get("/forca-operacional")
def forca_operacional(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Vagas de atividade-fim do QPO contra quem está nela, por lotação.

    O card de efetivo operacional divide operacionais pelo efetivo existente e,
    por isso, não enxerga vaga: abrir uma estação com 15 vagas não mexe no
    percentual dele. Aqui o denominador são as vagas operacionais do QPO, e o
    claro que sai é o da atividade-fim — foi a conta pedida para a EB Tremembé
    em 11/09/2026.

    As duas pontas vêm de efetivo_regras.py (SQL_VAGA_OPERACIONAL no QPO,
    SQL_OPERACIONAL no efetivo), para vaga e militar serem contados pelo mesmo
    critério. Lotação sem vaga nem operacional — o ADM — não aparece.
    """
    check_access(current_user)

    vagas = {
        r["parte"]: int(r["vagas"] or 0)
        for r in db.execute(text(f"""
            SELECT {SQL_PARTE_QPO}                                  AS parte,
                   SUM(vagas) FILTER (WHERE {SQL_VAGA_OPERACIONAL}) AS vagas
              FROM b1.qpo_funcoes
             GROUP BY 1
        """)).mappings().all()
    }
    operacionais = {
        r["parte"]: int(r["operacional"])
        for r in db.execute(text(f"""
            SELECT {SQL_PARTE}                               AS parte,
                   COUNT(*) FILTER (WHERE {SQL_OPERACIONAL}) AS operacional
              FROM b1.efetivo
             WHERE ativo = true
             GROUP BY 1
        """)).mappings().all()
    }

    def linha(rotulo, v, o):
        return {
            "lotacao": rotulo,
            "vagas_operacionais": v,
            "operacional": o,
            "claro": v - o,
            "perc_operacional": round(100 * o / v, 1) if v else None,
        }

    out = []
    for parte in ("1°Sgb", "2°Sgb", "3°Sgb", "4°Sgb") + PARTES_EM + ("Outros",):
        v, o = vagas.get(parte, 0), operacionais.get(parte, 0)
        if v or o:
            out.append(linha(parte, v, o))

    out.append(linha(
        "TOTAL GERAL",
        sum(r["vagas_operacionais"] for r in out),
        sum(r["operacional"] for r in out),
    ))
    return out


@router.get("/efetivo")
def listar_efetivo(
    lotacao: Optional[str] = Query(None),
    posto_grad: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    check_access(current_user)
    base = "FROM b1.vw_efetivo_classificado WHERE ativo = true"
    params = {}
    if lotacao:
        base += " AND lotacao = :lotacao"
        params["lotacao"] = lotacao
    if posto_grad:
        base += " AND posto_grad = :posto_grad"
        params["posto_grad"] = posto_grad
    if busca:
        base += " AND (nome ILIKE :busca OR re::text ILIKE :busca)"
        params["busca"] = f"%{busca}%"

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
    offset = (page - 1) * limit
    rows = db.execute(
        text(f"SELECT re, nome, posto_grad, lotacao, posto_qpo {base} ORDER BY ord_lotacao, posto_grad, nome LIMIT {limit} OFFSET {offset}"),
        params
    ).mappings().all()
    return {"total": total, "page": page, "limit": limit, "data": [dict(r) for r in rows]}


@router.get("/afastamentos")
def afastamentos_ativos(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    q = """
        SELECT
            a.re, e.nome, e.posto_grad, e.lotacao,
            a.motivo_grupo AS motivo,
            a.data_inicio, a.data_fim, a.quantidade_dias
        FROM b1.v_afastamentos_dedup a
        LEFT JOIN b1.vw_efetivo_classificado e ON e.re = a.re
        WHERE a.data_inicio <= CURRENT_DATE
          AND (a.data_fim IS NULL OR a.data_fim >= CURRENT_DATE)
          AND a.motivo_grupo != 'LICENCA PREMIO EM PECUNIA'
        ORDER BY a.motivo_grupo, e.nome
    """
    rows = db.execute(text(q)).mappings().all()
    return {"total": len(rows), "data": [dict(r) for r in rows]}


@router.get("/realocacao")
def realocacao_dados(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """QPO e existente por lotação e categoria, para o simulador de realocação.

    O EM sai em três linhas — SAT, COBOM e ADM — como no card de efetivo
    operacional. Numa linha só, o EM misturava um COBOM cheio (30/30) com um
    ADM oito acima do quadro e uma SAT nove abaixo; o simulador via a média e
    não tinha o que sugerir.

    COBOM vai marcado com `fixo`. É central de operações com guarnição
    dimensionada, não pool de efetivo: o equalizador automático não pode
    propor esvaziá-lo para igualar percentual com um SGB. As outras seis
    linhas continuam entrando na conta normalmente.
    """
    # Aba própria: quem vê Realocação não necessariamente vê Pessoal.
    if not pode_ver(current_user, "realocacao"):
        raise HTTPException(status_code=403, detail="Acesso negado")

    # QPO dos SGBs vem do agregado; o do EM só existe separado em
    # b1.qpo_funcoes, que guarda o quadro por seção (ver B1/importar_qpo_funcoes.py).
    qpo_sgb = db.execute(text("""
        SELECT lotacao,
               SUM(vagas) FILTER (WHERE categoria = 'Oficial')      AS qpo_of,
               SUM(vagas) FILTER (WHERE posto_grad = 'Subten/Sgt')  AS qpo_ss,
               SUM(vagas) FILTER (WHERE posto_grad = 'Cb/Sd')       AS qpo_cs
          FROM b1.qpo_vagas
         WHERE lotacao <> 'EM'
         GROUP BY lotacao
    """)).mappings().all()

    qpo_em = db.execute(text("""
        SELECT CASE WHEN subsecao ILIKE '%%COBOM%%' THEN 'COBOM'
                    WHEN secao ILIKE '%%Ativ T%%'   THEN 'SAT'
                    ELSE 'ADM' END                                   AS parte,
               COALESCE(SUM(vagas) FILTER (WHERE NOT a_designar
                                             AND categoria = 'Oficial'), 0)     AS qpo_of,
               COALESCE(SUM(vagas) FILTER (WHERE NOT a_designar
                                             AND posto_grad = 'Subten/Sgt'), 0) AS qpo_ss,
               COALESCE(SUM(vagas) FILTER (WHERE NOT a_designar
                                             AND posto_grad = 'Cb/Sd'), 0)      AS qpo_cs
          FROM b1.qpo_funcoes
         WHERE lotacao = 'EM'
         GROUP BY 1
    """)).mappings().all()

    # Existente: mesma classificação do card de efetivo operacional
    # (efetivo_regras.SQL_PARTE), para o simulador e o card não divergirem. Os
    # NATs contam na SAT, cujo QPO já os prevê, e saem dos SGBs, que não têm
    # vaga para eles. Antes a SAT aparecia 8 abaixo do quadro (1/6/5 contra
    # 2/13/6) e esses 8 inflavam o existente de 2°, 3° e 4° SGB.
    exist = db.execute(text(f"""
        SELECT {SQL_PARTE}                                           AS parte,
               COUNT(*) FILTER (WHERE posto_grad IN ('CAP PM','1. TEN PM','2. TEN PM',
                                                     'MAJ PM','TEN CEL PM','CEL PM',
                                                     'ASP OF PM'))   AS exist_of,
               COUNT(*) FILTER (WHERE posto_grad IN ('SUBTEN PM','1. SGT PM','2. SGT PM',
                                                     '3. SGT PM','STEN PM'))    AS exist_ss,
               COUNT(*) FILTER (WHERE posto_grad IN ('CB PM','SD PM','SD PM 2ª CL'))
                                                                    AS exist_cs
          FROM b1.efetivo
         WHERE ativo = true
         GROUP BY 1
    """)).mappings().all()

    qpo_map = {r["lotacao"]: r for r in qpo_sgb}
    qpo_map.update({r["parte"]: r for r in qpo_em})
    exist_map = {r["parte"]: r for r in exist}

    # Ordem fixa: SGBs, depois as três partes do EM. COBOM travado.
    ORDEM = [
        ("1°Sgb", "1°Sgb", False), ("2°Sgb", "2°Sgb", False),
        ("3°Sgb", "3°Sgb", False), ("4°Sgb", "4°Sgb", False),
        ("SAT", "EM · SAT", False), ("COBOM", "EM · COBOM", True),
        ("ADM", "EM · ADM", False),
    ]

    rows = []
    for chave, rotulo, fixo in ORDEM:
        q = qpo_map.get(chave, {})
        e = exist_map.get(chave, {})
        rows.append({
            "sgb":      rotulo,
            "chave":    chave,
            "fixo":     fixo,
            "qpo_of":   int(q.get("qpo_of")   or 0),
            "qpo_ss":   int(q.get("qpo_ss")   or 0),
            "qpo_cs":   int(q.get("qpo_cs")   or 0),
            "exist_of": int(e.get("exist_of") or 0),
            "exist_ss": int(e.get("exist_ss") or 0),
            "exist_cs": int(e.get("exist_cs") or 0),
        })

    return {"lotacoes": rows}


@router.get("/filtros")
def filtros_pessoal(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    lotacoes  = [r[0] for r in db.execute(text("SELECT DISTINCT lotacao FROM b1.vw_efetivo_classificado WHERE ativo ORDER BY lotacao")).fetchall()]
    postos    = [r[0] for r in db.execute(text("SELECT DISTINCT posto_grad FROM b1.vw_efetivo_classificado WHERE ativo ORDER BY posto_grad")).fetchall()]
    return {"lotacoes": lotacoes, "postos": postos}
