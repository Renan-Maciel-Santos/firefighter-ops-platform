"""
EAP — turmas do calendário da DEC, escala do efetivo e Ordem de Serviço (B/3).

Todo militar faz o EAP uma vez por ano, menos Ten Cel, Maj e Cap com CAO.
Tabelas em B3/migra_eap.sql; texto da OS em webapp/eap_documento.py.

Para cada militar a escala mostra o que impede ou atrapalha o EAP no período
da turma: IAS vencida na data da fase presencial (item 5 da OS: sem IAS em
dia não entra no presencial), afastamento que cruza o período (férias,
convalescença, LP...), restrição médica (faz só o EaD, 36 h) e se ele já
está em outra turma no ano.
"""
import io
import json
import os
import sys
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user
import eap_documento as doc

router = APIRouter(prefix="/eap", tags=["eap"])

ABA = "eap"
PUBLICOS = ("Oficiais", "Subten/Sgt", "Cb/Sd")
MODELO_PADRAO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "modelos", "eap_os_modelo.docx")

# posto_qpo (b1.vw_efetivo_classificado) que cada público de turma recebe.
PUBLICO_POSTOS = {
    "Oficiais":   ("Ten PM", "Cap PM"),
    "Subten/Sgt": ("Subten/Sgt",),
    "Cb/Sd":      ("Cb/Sd",),
}
# Dispensados pelo posto. Cap com CAO é dispensa individual (b3.eap_dispensa).
POSTOS_DISPENSADOS = ("Ten Cel PM", "Maj PM")


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


# ======================== TURMAS ========================

class PublicoTurma(BaseModel):
    publico: str
    turma: str          # número da DEC para este público: "V", "XIV"


class TurmaIn(BaseModel):
    ano: int
    publicos: list[PublicoTurma]
    ead_inicio: date
    ead_fim: date
    presencial_em: Optional[datetime] = None
    presencial_local: Optional[str] = None
    vagas: Optional[int] = None
    observacao: Optional[str] = None


def _valida_turma(db, t: TurmaIn, turma_id: int | None = None):
    if not t.publicos:
        raise HTTPException(400, "Marque ao menos um público.")
    vistos = set()
    for p in t.publicos:
        if p.publico not in PUBLICOS:
            raise HTTPException(400, f"Público inválido. Use: {', '.join(PUBLICOS)}")
        if p.publico in vistos:
            raise HTTPException(400, f"{p.publico} marcado duas vezes.")
        vistos.add(p.publico)
        p.turma = p.turma.strip().upper()
        if not p.turma:
            raise HTTPException(400, f"Informe o número da turma de {p.publico} (ex: XIV).")
    if t.ead_fim < t.ead_inicio:
        raise HTTPException(400, "O fim do EaD é antes do início.")
    # Tudo obrigatório, menos observação. Presencial (data e local) é o dos
    # praças; turma só de Oficiais não tem — o deles é na ESB, por convocação.
    so_oficiais = all(p.publico == "Oficiais" for p in t.publicos)
    faltam = [nome for nome, vazio in (
        ("data e hora do presencial", not so_oficiais and not t.presencial_em),
        ("local do presencial", not so_oficiais and not (t.presencial_local or "").strip()),
        ("vagas", not t.vagas or t.vagas <= 0),
    ) if vazio]
    if faltam:
        raise HTTPException(400, "Preencha: " + ", ".join(faltam) + ".")
    # Mesmo número para o mesmo público no mesmo ano é lançamento repetido.
    t.publicos.sort(key=lambda p: PUBLICOS.index(p.publico))
    for p in t.publicos:
        dup = db.execute(text("""
            SELECT 1 FROM b3.eap_turma
             WHERE ano = :ano AND id IS DISTINCT FROM :id
               AND publicos @> CAST(:alvo AS jsonb)
        """), {"ano": t.ano, "id": turma_id,
               "alvo": json.dumps([{"publico": p.publico, "turma": p.turma}])}).first()
        if dup:
            raise HTTPException(409, f"Já existe a Turma {p.turma} de {p.publico} em {t.ano}.")


def _params(t: TurmaIn) -> dict:
    d = t.model_dump()
    d["publicos"] = json.dumps(d["publicos"], ensure_ascii=False)
    return d


def _turma(db, turma_id: int):
    t = db.execute(text("SELECT * FROM b3.eap_turma WHERE id = :id"),
                   {"id": turma_id}).mappings().first()
    if not t:
        raise HTTPException(404, "Turma não encontrada")
    return t


def _postos(turma) -> list[str]:
    """posto_qpo que a turma recebe — a soma dos públicos marcados."""
    return sorted({q for p in turma["publicos"] for q in PUBLICO_POSTOS.get(p["publico"], ())})


@router.get("/turmas")
def listar_turmas(ano: int = Query(None), db: Session = Depends(get_db),
                  current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    if not ano:
        # Sem ano escolhido, abre no ano da turma em andamento ou da próxima.
        # Abrir sempre no ano corrente escondia a turma de fevereiro lançada
        # em outubro: quem entrava via 2026 vazio e não achava nada.
        ano = db.execute(text("""
            SELECT MIN(ano) FROM b3.eap_turma
             WHERE GREATEST(ead_fim, COALESCE(presencial_em::date, ead_fim)) >= CURRENT_DATE
        """)).scalar() or date.today().year
    turmas = db.execute(text("""
        SELECT t.*,
               COUNT(i.re)                          AS inscritos,
               COUNT(i.re) FILTER (WHERE i.escalado) AS escalados
          FROM b3.eap_turma t
          LEFT JOIN b3.eap_inscricao i ON i.turma_id = t.id
         WHERE t.ano = :ano
         GROUP BY t.id
         ORDER BY t.ead_inicio, t.id
    """), {"ano": ano}).mappings().all()

    # Quem precisa fazer no ano x quem já está escalado em alguma turma.
    resumo = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE obrigado)                AS obrigados,
               COUNT(*) FILTER (WHERE obrigado AND escalado)   AS escalados,
               COUNT(*) FILTER (WHERE obrigado AND NOT escalado) AS pendentes
          FROM (
            SELECT v.re,
                   (v.posto_qpo IS DISTINCT FROM 'Ten Cel PM'
                    AND v.posto_qpo IS DISTINCT FROM 'Maj PM'
                    AND d.re IS NULL)                            AS obrigado,
                   EXISTS (SELECT 1 FROM b3.eap_inscricao i
                             JOIN b3.eap_turma t ON t.id = i.turma_id
                            WHERE i.re = v.re AND t.ano = :ano AND i.escalado) AS escalado
              FROM b1.vw_efetivo_classificado v
              LEFT JOIN b3.eap_dispensa d ON d.re = v.re
          ) x
    """), {"ano": ano}).mappings().first()

    anos = [r[0] for r in db.execute(text(
        "SELECT DISTINCT ano FROM b3.eap_turma ORDER BY ano DESC")).fetchall()]
    return {"ano": ano, "anos": anos, "resumo": dict(resumo),
            "turmas": [dict(t) for t in turmas], "publicos": PUBLICOS}


@router.post("/turmas")
def criar_turma(t: TurmaIn, db: Session = Depends(get_db),
                current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    _valida_turma(db, t)
    novo = db.execute(text("""
        INSERT INTO b3.eap_turma (ano, publicos, ead_inicio, ead_fim, presencial_em,
                                  presencial_local, vagas, observacao, criado_por)
        VALUES (:ano, CAST(:publicos AS jsonb), :ead_inicio, :ead_fim, :presencial_em,
                :presencial_local, :vagas, :observacao, :por)
        RETURNING id
    """), {**_params(t), "por": current_user.nome}).scalar()
    db.commit()
    return {"id": novo}


@router.put("/turmas/{turma_id}")
def editar_turma(turma_id: int, t: TurmaIn, db: Session = Depends(get_db),
                 current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    _turma(db, turma_id)
    _valida_turma(db, t, turma_id)
    db.execute(text("""
        UPDATE b3.eap_turma
           SET ano = :ano, publicos = CAST(:publicos AS jsonb), ead_inicio = :ead_inicio,
               ead_fim = :ead_fim, presencial_em = :presencial_em,
               presencial_local = :presencial_local, vagas = :vagas,
               observacao = :observacao, atualizado_em = now()
         WHERE id = :id
    """), {**_params(t), "id": turma_id})
    db.commit()
    return {"ok": True}


@router.delete("/turmas/{turma_id}")
def excluir_turma(turma_id: int, db: Session = Depends(get_db),
                  current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    _turma(db, turma_id)
    db.execute(text("DELETE FROM b3.eap_turma WHERE id = :id"), {"id": turma_id})
    db.commit()
    return {"ok": True}


# ======================== SITUAÇÃO DO MILITAR ========================

def _periodo(turma) -> tuple[date, date, date]:
    """(início, fim, data de referência da IAS) da turma.

    A IAS precisa estar em dia na fase presencial; sem data de presencial,
    vale o fim do EaD.
    """
    ini = turma["ead_inicio"]
    pres = turma["presencial_em"].date() if turma["presencial_em"] else None
    fim = max(turma["ead_fim"], pres) if pres else turma["ead_fim"]
    return ini, fim, pres or turma["ead_fim"]


def _situacao(db, filtro: str, params: dict, turma=None, ano: int | None = None,
              limite: int | None = None, ordem: str = "a.ordem_geral NULLS LAST, b.nome"):
    """Militares do efetivo ativo com tudo o que a escala precisa saber."""
    hoje = date.today()
    if turma:
        ini, fim, ref_ias = _periodo(turma)
        ano = turma["ano"]
    else:
        ini = fim = ref_ias = hoje
    ano = ano or hoje.year
    p = {**params, "ini": ini, "fim": fim, "ano": ano}
    lim = f"LIMIT {int(limite)}" if limite else ""

    rows = db.execute(text(f"""
        WITH b AS (
            SELECT e.re, e.re_dv, e.nome, e.posto_grad, e.cod_opm_atual, e.opm_atual,
                   v.lotacao, v.ord_lotacao, v.posto_qpo
              FROM b1.efetivo e
              JOIN b1.vw_efetivo_classificado v ON v.re = e.re
             WHERE e.ativo AND ({filtro})
        )
        SELECT b.*,
               ias.validade AS ias_validade,
               d.motivo     AS dispensa,
               (SELECT json_agg(json_build_object(
                         'motivo', af.motivo_grupo, 'inicio', af.data_inicio, 'fim', af.data_fim)
                         ORDER BY af.data_inicio)
                  FROM b1.v_afastamentos_dedup af
                 WHERE af.re = b.re
                   AND af.data_inicio <= :fim
                   AND (af.data_fim IS NULL OR af.data_fim >= :ini)
                   AND af.motivo_grupo <> 'LICENCA PREMIO EM PECUNIA') AS afastamentos,
               -- SIGS: "Apto com Restrição" (faz só o EaD) e LTS. "Apto Pleno" é o
               -- fim de um afastamento, não restrição — mesmo critério da aba Saúde.
               (SELECT json_agg(json_build_object(
                         'tipo', r.observacao, 'inicio', r.data_inicial, 'fim', r.data_final)
                         ORDER BY r.data_inicial)
                  FROM b1.restricoes r
                 WHERE r.re = b.re
                   AND r.observacao <> 'Apto Pleno'
                   AND r.data_inicial <= :fim
                   AND (r.data_final IS NULL OR r.data_final >= :ini)) AS restricoes,
               (SELECT json_agg(json_build_object(
                         'turma_id', t.id, 'publicos', t.publicos,
                         'escalado', i.escalado, 'ead_inicio', t.ead_inicio)
                         ORDER BY t.ead_inicio)
                  FROM b3.eap_inscricao i
                  JOIN b3.eap_turma t ON t.id = i.turma_id
                 WHERE i.re = b.re AND t.ano = :ano) AS turmas_ano
          FROM b
          LEFT JOIN LATERAL (SELECT MAX(data_validade) AS validade
                               FROM b1.ias_inspecao WHERE re = b.re) ias ON true
          LEFT JOIN b3.eap_dispensa d ON d.re = b.re
          LEFT JOIN b1.vw_antiguidade a ON a.re = b.re
         ORDER BY {ordem}
         {lim}
    """), p).mappings().all()

    saida = []
    for r in rows:
        m = dict(r)
        val = m["ias_validade"]
        if val is None:
            m["ias"] = "SEM IAS"
        elif val < hoje:
            m["ias"] = "ATRASADA"
        elif val < ref_ias:
            m["ias"] = "VENCE ANTES"   # em dia hoje, vencida no presencial
        else:
            m["ias"] = "EM DIA"
        m["ias_referencia"] = ref_ias
        m["afastamentos"] = m["afastamentos"] or []
        m["restricoes"] = m["restricoes"] or []
        m["turmas_ano"] = m["turmas_ano"] or []
        if m["posto_qpo"] in POSTOS_DISPENSADOS:
            m["dispensa"] = f"{m['posto_qpo'].replace(' PM', '')} — dispensado pelo posto"
        m["re_completo"] = f"{m['re']}-{m['re_dv']}" if m["re_dv"] else str(m["re"])
        if turma:
            m["publico_ok"] = m["posto_qpo"] in _postos(turma)
        saida.append(m)
    return saida


@router.get("/militares")
def buscar_militares(q: str = Query(..., min_length=1), turma_id: Optional[int] = None,
                     db: Session = Depends(get_db),
                     current_user: Usuario = Depends(get_current_user)):
    """Autocomplete: RE (começo) ou nome (qualquer parte)."""
    check_access(current_user)
    turma = _turma(db, turma_id) if turma_id else None
    q = q.strip()
    if q.isdigit():
        return _situacao(db, "e.re::text LIKE :q", {"q": q + "%"}, turma, limite=15, ordem="b.re")
    # Quem começa com o texto vem antes de quem só o contém ("ANA" antes de "JULIANA").
    return _situacao(db, "e.nome ILIKE :q", {"q": "%" + q + "%", "q_ini": q + "%"}, turma,
                     limite=15, ordem="b.nome ILIKE :q_ini DESC, b.nome")


@router.get("/turmas/{turma_id}/inscritos")
def inscritos(turma_id: int, db: Session = Depends(get_db),
              current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    turma = _turma(db, turma_id)
    lista = _situacao(db, "e.re IN (SELECT re FROM b3.eap_inscricao WHERE turma_id = :tid)",
                      {"tid": turma_id}, turma)
    esc = {r["re"]: r["escalado"] for r in db.execute(text(
        "SELECT re, escalado FROM b3.eap_inscricao WHERE turma_id = :tid"),
        {"tid": turma_id}).mappings()}
    for m in lista:
        m["escalado"] = esc.get(m["re"], False)
    # Inscrito que saiu do efetivo ativo some do _situacao; avisa em vez de esconder.
    fora = sorted(set(esc) - {m["re"] for m in lista})
    return {"turma": dict(turma), "inscritos": lista, "fora_do_efetivo": fora}


@router.get("/pendentes")
def pendentes(ano: int = Query(None), turma_id: Optional[int] = None,
              db: Session = Depends(get_db),
              current_user: Usuario = Depends(get_current_user)):
    """Quem precisa fazer o EAP no ano e ainda não está escalado em turma nenhuma."""
    check_access(current_user)
    turma = _turma(db, turma_id) if turma_id else None
    ano = turma["ano"] if turma else (ano or date.today().year)
    filtro = """
        v.posto_qpo IS DISTINCT FROM 'Ten Cel PM' AND v.posto_qpo IS DISTINCT FROM 'Maj PM'
        AND e.re NOT IN (SELECT re FROM b3.eap_dispensa)
        AND e.re NOT IN (SELECT i.re FROM b3.eap_inscricao i JOIN b3.eap_turma t ON t.id = i.turma_id
                          WHERE t.ano = :ano_p AND i.escalado)
    """
    params = {"ano_p": ano}
    if turma:
        filtro += " AND v.posto_qpo = ANY(:postos)"
        params["postos"] = _postos(turma)
    return _situacao(db, filtro, params, turma, ano=ano,
                     ordem="b.ord_lotacao, a.ordem_geral NULLS LAST, b.nome")


# ======================== ESCALA ========================

class InscricaoIn(BaseModel):
    re: int
    escalado: bool = False


class EscaladoIn(BaseModel):
    escalado: bool


@router.post("/turmas/{turma_id}/inscritos")
def inscrever(turma_id: int, dados: InscricaoIn, db: Session = Depends(get_db),
              current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    _turma(db, turma_id)
    if not db.execute(text("SELECT 1 FROM b1.efetivo WHERE re = :re AND ativo"),
                      {"re": dados.re}).first():
        raise HTTPException(404, f"RE {dados.re} não está no efetivo ativo.")
    db.execute(text("""
        INSERT INTO b3.eap_inscricao (turma_id, re, escalado, criado_por)
        VALUES (:tid, :re, :esc, :por)
        ON CONFLICT (turma_id, re) DO UPDATE SET escalado = EXCLUDED.escalado, atualizado_em = now()
    """), {"tid": turma_id, "re": dados.re, "esc": dados.escalado, "por": current_user.nome})
    db.commit()
    return {"ok": True}


@router.patch("/turmas/{turma_id}/inscritos/{re}")
def marcar_escalado(turma_id: int, re: int, dados: EscaladoIn, db: Session = Depends(get_db),
                    current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    n = db.execute(text("""
        UPDATE b3.eap_inscricao SET escalado = :esc, atualizado_em = now()
         WHERE turma_id = :tid AND re = :re
    """), {"tid": turma_id, "re": re, "esc": dados.escalado}).rowcount
    db.commit()
    if not n:
        raise HTTPException(404, "Militar não está nesta turma")
    return {"ok": True}


@router.delete("/turmas/{turma_id}/inscritos/{re}")
def desinscrever(turma_id: int, re: int, db: Session = Depends(get_db),
                 current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    db.execute(text("DELETE FROM b3.eap_inscricao WHERE turma_id = :tid AND re = :re"),
               {"tid": turma_id, "re": re})
    db.commit()
    return {"ok": True}


@router.post("/dispensa/{re}")
def dispensar_cao(re: int, db: Session = Depends(get_db),
                  current_user: Usuario = Depends(get_current_user)):
    """Capitão com CAO. Outros postos não têm dispensa individual."""
    check_access(current_user)
    posto = db.execute(text("SELECT posto_qpo FROM b1.vw_efetivo_classificado WHERE re = :re"),
                       {"re": re}).scalar()
    if posto != "Cap PM":
        raise HTTPException(400, "Dispensa por CAO é só para Capitão.")
    db.execute(text("""
        INSERT INTO b3.eap_dispensa (re, motivo, criado_por) VALUES (:re, 'CAO', :por)
        ON CONFLICT (re) DO NOTHING
    """), {"re": re, "por": current_user.nome})
    db.commit()
    return {"ok": True}


@router.delete("/dispensa/{re}")
def remover_dispensa(re: int, db: Session = Depends(get_db),
                     current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    db.execute(text("DELETE FROM b3.eap_dispensa WHERE re = :re"), {"re": re})
    db.commit()
    return {"ok": True}


# ======================== ORDEM DE SERVIÇO ========================

def _turmas(db, ids: list[int]):
    if not ids:
        raise HTTPException(400, "Escolha ao menos uma turma.")
    ts = db.execute(text("SELECT * FROM b3.eap_turma WHERE id = ANY(:ids) ORDER BY ead_inicio, id"),
                    {"ids": ids}).mappings().all()
    if len(ts) != len(set(ids)):
        raise HTTPException(404, "Turma não encontrada")
    if len({t["ano"] for t in ts}) > 1:
        raise HTTPException(400, "As turmas da OS precisam ser do mesmo ano.")
    return ts


def _escalados(db, ids: list[int]):
    return db.execute(text("""
        SELECT e.re, e.re_dv, e.nome, e.posto_grad, e.cod_opm_atual, v.posto_qpo
          FROM b1.efetivo e
          LEFT JOIN b1.vw_efetivo_classificado v ON v.re = e.re
          LEFT JOIN b1.vw_antiguidade a ON a.re = e.re
         WHERE e.re IN (SELECT re FROM b3.eap_inscricao WHERE turma_id = ANY(:ids) AND escalado)
         ORDER BY a.ordem_geral NULLS LAST, e.nome
    """), {"ids": ids}).mappings().all()


def _modelo(db, ano: int) -> tuple[bytes, str]:
    r = db.execute(text("SELECT arquivo FROM b3.eap_modelo WHERE ano = :ano"), {"ano": ano}).first()
    if r:
        return bytes(r[0]), f"modelo de {ano}"
    with open(MODELO_PADRAO, "rb") as f:
        return f.read(), "modelo padrão"


OFICIAIS = ("Ten Cel PM", "Maj PM", "Cap PM", "Ten PM")


def _presenciais(esc) -> tuple[bool, bool]:
    """(tem praça, tem oficial) entre os escalados.

    Decide os itens do presencial pela relação, não pela turma: uma OS com
    a turma de Oficiais aberta mas nenhum oficial escalado não leva o item
    da ESB (na OS 073/26 ele estava lá à toa).
    """
    of = [e["posto_qpo"] in OFICIAIS for e in esc]
    return (not all(of)) if of else False, any(of)


# Como cada público é escrito no texto da OS.
PUBLICO_NA_OS = {"Oficiais": "Oficiais",
                 "Subten/Sgt": "Subten/Sgt PM", "Cb/Sd": "Cb/Sd PM"}


def _publicos(ts) -> list[dict]:
    """Públicos das turmas da OS, sem repetir, Oficiais primeiro."""
    vistos = {}
    for t in ts:
        for p in t["publicos"]:
            vistos.setdefault((p["publico"], p["turma"]), p)
    return sorted(vistos.values(), key=lambda p: PUBLICOS.index(p["publico"]))


def _publico_pracas(ts) -> str:
    return " e ".join(dict.fromkeys(PUBLICO_NA_OS[p["publico"]] for p in _publicos(ts)
                                    if p["publico"] != "Oficiais"))


@router.get("/os/sugestao")
def sugestao_os(turmas: str = Query(..., description="ids separados por vírgula"),
                db: Session = Depends(get_db),
                current_user: Usuario = Depends(get_current_user)):
    """Campos da OS já preenchidos a partir das turmas e da última OS emitida."""
    check_access(current_user)
    ids = [int(x) for x in turmas.split(",") if x.strip()]
    ts = _turmas(db, ids)
    ano = ts[0]["ano"]
    hoje = date.today()
    esc = _escalados(db, ids)

    ultima = db.execute(text("""
        SELECT numero, campos FROM b3.eap_os ORDER BY gerado_em DESC LIMIT 1
    """)).mappings().first()
    prox = db.execute(text("SELECT MAX(numero) FROM b3.eap_os WHERE ano = :ano"),
                      {"ano": hoje.year}).scalar()
    campos_ant = (ultima["campos"] if ultima else {}) or {}

    partes = [f"Turma {p['turma']} para {PUBLICO_NA_OS[p['publico']]}" for p in _publicos(ts)]
    assunto = f"EAP {ano} {doc.junta(partes)}."

    inicios = {t["ead_inicio"] for t in ts}
    fins = {t["ead_fim"] for t in ts}
    periodo = f"{doc.data_militar(min(inicios))} a {doc.data_militar(max(fins))}"
    pracas = [t for t in ts if any(p["publico"] != "Oficiais" for p in t["publicos"])]
    tem_pracas, tem_oficiais = _presenciais(esc)
    pres = next((t for t in pracas if t["presencial_em"]), None)

    # Quem assina é sempre o Subcomando, mas a pessoa muda: sem Maj/Ten Cel no
    # quartel, um Capitão responde como Subcomandante Interino. A lista vai
    # em ordem de antiguidade para o B/3 escolher quem está no posto.
    oficiais = db.execute(text("""
        SELECT e.nome, e.posto_grad, v.posto_qpo
          FROM b1.efetivo e
          JOIN b1.vw_efetivo_classificado v ON v.re = e.re
          LEFT JOIN b1.vw_antiguidade a ON a.re = e.re
         WHERE e.ativo AND v.posto_qpo IN ('Ten Cel PM', 'Maj PM', 'Cap PM', 'Ten PM')
         ORDER BY a.ordem_geral NULLS LAST, e.nome
    """)).mappings().all()
    assinantes = [{
        "nome": o["nome"],
        "posto": doc.POSTOS.get(o["posto_grad"], o["posto_grad"]),
        "funcao": doc.POSTOS.get(o["posto_grad"], o["posto_grad"]) + " Subcomandante"
                  + ("" if o["posto_qpo"] in ("Ten Cel PM", "Maj PM") else " Interino"),
    } for o in oficiais]

    _, origem = _modelo(db, ano)
    return {
        "assinantes": assinantes,
        "campos": {
            "data_extenso": doc.data_extenso(hoje),
            "numero": f"{(prox or 0) + 1:03d}" if prox else "",
            "ano2": f"{hoje.year % 100:02d}",
            "ano": str(ano),
            "destinatarios": doc.texto_destinatarios([e["cod_opm_atual"] for e in esc]),
            "assunto": assunto,
            "periodo_ead": periodo,
            "publico_pracas": _publico_pracas(ts),
            "presencial_pracas": doc.dtg(pres["presencial_em"]) if pres else "",
            "local_pracas": (pres or {}).get("presencial_local") or campos_ant.get("local_pracas", ""),
            "assinante_nome": campos_ant.get("assinante_nome", ""),
            "assinante_funcao": campos_ant.get("assinante_funcao", ""),
        },
        "militares": [doc.linha_militar(e["posto_grad"], e["re"], e["re_dv"], e["nome"]) for e in esc],
        "sem_digito": [e["re"] for e in esc if not e["re_dv"]],
        "periodos_diferentes": len(inicios) > 1 or len(fins) > 1,
        "tem_pracas": tem_pracas,
        "tem_oficiais": tem_oficiais,
        "modelo": origem,
    }


class GerarOsIn(BaseModel):
    turmas: list[int]
    campos: dict[str, str]


@router.post("/os/gerar")
def gerar_os(dados: GerarOsIn, db: Session = Depends(get_db),
             current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    ts = _turmas(db, dados.turmas)
    esc = _escalados(db, dados.turmas)
    if not esc:
        raise HTTPException(400, "Nenhum militar escalado nas turmas escolhidas.")
    campos = {k: (v or "").strip() for k, v in dados.campos.items()}
    if not campos.get("numero", "").isdigit():
        raise HTTPException(400, "Informe o número da OS (só dígitos, ex: 073).")

    modelo, _ = _modelo(db, ts[0]["ano"])
    conteudo = doc.gerar(
        modelo, campos,
        [doc.linha_militar(e["posto_grad"], e["re"], e["re_dv"], e["nome"]) for e in esc],
        *_presenciais(esc),
    )
    db.execute(text("""
        INSERT INTO b3.eap_os (ano, numero, turma_ids, campos, gerado_por)
        VALUES (:ano, :num, :ids, CAST(:campos AS jsonb), :por)
    """), {"ano": 2000 + int(campos.get("ano2") or date.today().year % 100),
           "num": int(campos["numero"]), "ids": dados.turmas,
           "campos": json.dumps(campos, ensure_ascii=False), "por": current_user.nome})
    db.commit()

    nome = f"{campos['numero']}_{campos.get('ano2', '')} EAP {ts[0]['ano']} " + \
           " e ".join(f"Turma {p['turma']} {p['publico'].replace('/', ' e ')}" for p in _publicos(ts)) + ".docx"
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )


# ======================== MODELO DO ANO ========================

@router.get("/modelo")
def baixar_modelo(ano: int = Query(None), db: Session = Depends(get_db),
                  current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    ano = ano or date.today().year
    conteudo, _ = _modelo(db, ano)
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=modelo_os_eap_{ano}.docx"},
    )


@router.get("/modelo/info")
def info_modelo(ano: int = Query(None), db: Session = Depends(get_db),
                current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    ano = ano or date.today().year
    r = db.execute(text("SELECT nome_arquivo, enviado_em, enviado_por FROM b3.eap_modelo WHERE ano = :ano"),
                   {"ano": ano}).mappings().first()
    return {"ano": ano, "proprio": bool(r), **(dict(r) if r else {})}


@router.post("/modelo")
async def enviar_modelo(ano: int = Query(...), arquivo: UploadFile = File(...),
                        db: Session = Depends(get_db),
                        current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    conteudo = await arquivo.read()
    if not (arquivo.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "Envie o modelo em .docx (no Word: Salvar como > Documento do Word).")
    try:
        achados = doc.campos_do_modelo(conteudo)
    except Exception:
        raise HTTPException(400, "Não consegui abrir o arquivo como .docx.")
    faltam = [c for c in doc.OBRIGATORIOS if c not in achados]
    if faltam:
        raise HTTPException(400, "O modelo não tem os campos: " +
                            ", ".join("{{" + c + "}}" for c in faltam))
    db.execute(text("""
        INSERT INTO b3.eap_modelo (ano, arquivo, nome_arquivo, enviado_por)
        VALUES (:ano, :arq, :nome, :por)
        ON CONFLICT (ano) DO UPDATE SET arquivo = EXCLUDED.arquivo, nome_arquivo = EXCLUDED.nome_arquivo,
                                        enviado_em = now(), enviado_por = EXCLUDED.enviado_por
    """), {"ano": ano, "arq": conteudo, "nome": arquivo.filename, "por": current_user.nome})
    db.commit()
    return {"ok": True, "campos": sorted(achados)}


@router.delete("/modelo")
def remover_modelo(ano: int = Query(...), db: Session = Depends(get_db),
                   current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    db.execute(text("DELETE FROM b3.eap_modelo WHERE ano = :ano"), {"ano": ano})
    db.commit()
    return {"ok": True}
