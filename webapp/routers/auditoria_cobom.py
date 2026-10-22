"""
Auditoria de qualidade do atendimento 193 — COBOM (aba da B/3).

Junta num formulário só o que a B/3 fazia em dois arquivos no share: a
planilha "Controle de Monitorias QUALIDADE" (14 itens S/N e a nota) e a
"FICHA DE AVALIAÇÃO" em Word, uma por militar. Tabela: b3.auditoria_cobom
(DDL em B3/create_auditoria_cobom.sql).

TODA PERGUNTA É "SIM = CONFORME"
Na planilha, três colunas eram invertidas: "Utiliza abreviaturas não
convencionais?" pontuava com S, e nas conformidades graves o S marcava a FALHA
(`IF(T="S",-100)`). No formulário, NÃO abre o campo da inconformidade — então
toda pergunta foi escrita para que SIM seja o atendimento correto. O sentido
de cada item é o mesmo da planilha; só a pergunta virou do avesso.

NOTA
Mesma fórmula da coluna V da planilha: os dez itens comuns somam 100, e cada
grave não cumprido desconta (50 ou 100). O cabeçalho da planilha diz
"conformidades graves — 0 pontos", então a nota não fica negativa.
"""

import json
import os
import sys
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from efetivo_regras import EM_COBOM
from routers.auth import get_current_user

router = APIRouter(prefix="/auditoria-cobom", tags=["auditoria-cobom"])

ABA = "auditoria_cobom"

# (chave, coluna da planilha, pergunta, peso, grave)
# Peso dos comuns: pontos que o SIM vale. Peso dos graves: quanto o NÃO desconta.
ITENS = (
    ("abertura",     "H", "Utiliza a verbalização padrão de abertura e de finalização do atendimento?", 5, False),
    ("tempo",        "I", "Atende ao solicitante no tempo necessário para a coleta célere e eficaz dos dados?", 5, False),
    ("abreviaturas", "J", "Evita abreviaturas não convencionais?", 5, False),
    ("dados",        "K", "Questiona e insere os dados: município, telefone, logradouro, complemento e referência?", 10, False),
    ("historico",    "L", "Registra no histórico todos os dados importantes para a compreensão da ocorrência?", 20, False),
    ("encerramento", "M", "Encerra a ligação ao perceber trote, após gerar a ocorrência ou quando o solicitante não se comunica mais?", 5, False),
    ("orientacao",   "N", "Orienta adequadamente o solicitante?", 20, False),
    ("cordialidade", "O", "Mantém cordialidade, atenção, educação e empatia durante o atendimento?", 10, False),
    ("objetividade", "P", "Direciona o atendimento por meio de perguntas objetivas?", 10, False),
    ("imparcialidade", "Q", "Atende ao solicitante de forma imparcial, sem se envolver na ocorrência?", 10, False),
    ("despacho",     "R", "Diante de dúvida ou insistência, mesmo de outro município, gera ocorrência ou reitera para o despacho de viatura?", 50, True),
    ("normas",       "S", "Cumpre o normatizado nas instruções vigentes do COBOM (transferência de ligações, consulta de RE, padronização de endereço não localizado no SIOPM)?", 100, True),
    ("imagem",       "T", "Preserva a imagem do Corpo de Bombeiros, sem comprometê-la?", 100, True),
    ("auto_impacto", "U", "Adere aos procedimentos de auto impacto?", 100, True),
)
CHAVES = tuple(i[0] for i in ITENS)

PARECERES = ("APROVADO", "APROVADO COM ORIENTAÇÕES", "REPROVADO")


def check_access(user: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


def calcular_nota(respostas: dict) -> int:
    nota = 0
    for chave, _col, _perg, peso, grave in ITENS:
        conforme = respostas[chave]["conforme"]
        if grave and not conforme:
            nota -= peso
        elif not grave and conforme:
            nota += peso
    return max(nota, 0)


class Resposta(BaseModel):
    conforme: bool
    obs: str | None = None


class Audio(BaseModel):
    ocorrencia: str | None = None
    audio: str | None = None
    data: date | None = None
    tma: str | None = None


class Ficha(BaseModel):
    re: int
    informacao_num: str | None = None
    data_servico: date
    turno: str | None = None
    equipe: str | None = None
    posto_atendimento: str | None = None
    avaliador_1: str | None = None
    avaliador_2: str | None = None
    audios: list[Audio] = Field(default_factory=list)
    respostas: dict[str, Resposta]
    parecer: str
    observacoes: str | None = None
    prov_encarregado: str | None = None
    prov_chefe: str | None = None
    prov_supervisao: str | None = None


def _limpo(s: str | None) -> str | None:
    s = (s or "").strip()
    return s or None


def _validar(f: Ficha, db: Session) -> tuple[dict, dict, list]:
    """Devolve (militar, respostas normalizadas, áudios) ou levanta 400."""
    militar = db.execute(text("""
        SELECT re, posto_grad, nome FROM b1.efetivo
        WHERE re = :re AND cod_opm_atual = :cobom
    """), {"re": f.re, "cobom": EM_COBOM}).mappings().first()
    if not militar:
        # Só quem está no código do COBOM é avaliado. A edição reconfere a
        # lotação também: quem saiu do COBOM fica com as fichas que já tem,
        # mas não ganha ficha nova nem alterada.
        raise HTTPException(400, "Militar não está lotado no COBOM")

    faltando = [c for c in CHAVES if c not in f.respostas]
    if faltando:
        raise HTTPException(400, f"Responda todas as perguntas ({len(faltando)} em aberto)")

    respostas = {}
    for chave in CHAVES:
        r = f.respostas[chave]
        obs = _limpo(r.obs)
        if not r.conforme and not obs:
            n = CHAVES.index(chave) + 1
            raise HTTPException(400, f"Item {n}: descreva a inconformidade")
        respostas[chave] = {"conforme": r.conforme, "obs": None if r.conforme else obs}

    if f.parecer not in PARECERES:
        raise HTTPException(400, "Parecer inválido")

    audios = [a.model_dump(mode="json") for a in f.audios
              if _limpo(a.ocorrencia) or _limpo(a.audio)]
    return dict(militar), respostas, audios


def _params(f: Ficha, militar: dict, respostas: dict, audios: list) -> dict:
    return {
        "re": militar["re"], "posto_grad": militar["posto_grad"], "nome": militar["nome"],
        "informacao_num": _limpo(f.informacao_num),
        "data_servico": f.data_servico,
        "turno": _limpo(f.turno), "equipe": _limpo(f.equipe),
        "posto_atendimento": _limpo(f.posto_atendimento),
        "avaliador_1": _limpo(f.avaliador_1), "avaliador_2": _limpo(f.avaliador_2),
        "audios": json.dumps(audios, ensure_ascii=False),
        "respostas": json.dumps(respostas, ensure_ascii=False),
        "nota": calcular_nota(respostas),
        "parecer": f.parecer,
        "observacoes": _limpo(f.observacoes),
        "prov_encarregado": _limpo(f.prov_encarregado),
        "prov_chefe": _limpo(f.prov_chefe),
        "prov_supervisao": _limpo(f.prov_supervisao),
    }


@router.get("/itens")
def itens(current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    return {
        "itens": [{"chave": c, "coluna": col, "pergunta": p, "peso": peso, "grave": g}
                  for c, col, p, peso, g in ITENS],
        "pareceres": PARECERES,
    }


@router.get("/militares")
def militares(db: Session = Depends(get_db),
              current_user: Usuario = Depends(get_current_user)):
    """Só os militares ativos do código do COBOM (efetivo_regras.EM_COBOM)."""
    check_access(current_user)
    rows = db.execute(text("""
        SELECT re, posto_grad, nome FROM b1.efetivo
        WHERE cod_opm_atual = :cobom AND ativo
        ORDER BY CASE
                   WHEN posto_grad ILIKE 'SUBTEN%' THEN 1
                   WHEN posto_grad ILIKE '1.%SGT%' THEN 2
                   WHEN posto_grad ILIKE '2.%SGT%' THEN 3
                   WHEN posto_grad ILIKE '3.%SGT%' THEN 4
                   WHEN posto_grad ILIKE 'CB%'     THEN 5
                   WHEN posto_grad ILIKE 'SD%'     THEN 6
                   ELSE 0 END, nome
    """), {"cobom": EM_COBOM}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/resumo")
def resumo(mes: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
           db: Session = Depends(get_db),
           current_user: Usuario = Depends(get_current_user)):
    """Equivalente ao "Painel Global de Qualidade" da planilha, para o mês."""
    check_access(current_user)
    ini = date.fromisoformat(mes + "-01")
    p = {"ini": ini, "cobom": EM_COBOM}
    fichas = db.execute(text("""
        SELECT re, nota, parecer, respostas, jsonb_array_length(audios) AS n_audios
        FROM b3.auditoria_cobom
        WHERE data_servico >= :ini AND data_servico < (:ini + interval '1 month')
    """), p).mappings().all()
    efetivo = db.execute(text(
        "SELECT count(*) FROM b1.efetivo WHERE cod_opm_atual = :cobom AND ativo"
    ), p).scalar()

    erros = {c: 0 for c in CHAVES}
    for f in fichas:
        for c in CHAVES:
            r = (f["respostas"] or {}).get(c)
            if r and not r.get("conforme"):
                erros[c] += 1

    n = len(fichas)
    return {
        "fichas": n,
        "audios": sum(f["n_audios"] for f in fichas),
        "monitorados": len({f["re"] for f in fichas}),
        "efetivo": efetivo,
        "media": round(sum(f["nota"] for f in fichas) / n, 1) if n else None,
        "pareceres": {p_: sum(1 for f in fichas if f["parecer"] == p_) for p_ in PARECERES},
        "erros": [{"chave": c, "erros": erros[c]} for c in CHAVES],
    }


# Agrupamentos da aba Estatísticas: quantos meses cada período tem.
AGRUPAMENTOS = {"mes": 1, "bimestre": 2, "trimestre": 3, "semestre": 6, "ano": 12}
MESES_ABREV = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _rotulo_periodo(inicio: date, meses: int) -> str:
    a = inicio.year
    if meses == 1:
        return f"{MESES_ABREV[inicio.month - 1]}/{a % 100:02d}"
    if meses == 12:
        return str(a)
    n = (inicio.month - 1) // meses + 1
    nome = {2: "bim", 3: "tri", 6: "sem"}[meses]
    return f"{n}º {nome}/{a % 100:02d}"


def _inicio_periodo(d: date, meses: int) -> date:
    return date(d.year, (d.month - 1) // meses * meses + 1, 1)


def _soma_meses(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


@router.get("/estatisticas")
def estatisticas(de: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                 ate: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                 agrupar: str = Query("mes"),
                 db: Session = Depends(get_db),
                 current_user: Usuario = Depends(get_current_user)):
    """Score (nota) por período e por PM, entre os meses `de` e `ate`.

    Períodos sem ficha aparecem vazios — um buraco na série é informação
    (mês sem monitoria), não algo a esconder. Na lista por PM entram também
    os militares ativos do COBOM sem nenhuma ficha no intervalo.
    """
    check_access(current_user)
    if agrupar not in AGRUPAMENTOS:
        raise HTTPException(400, f"Agrupamento inválido: {', '.join(AGRUPAMENTOS)}")
    meses = AGRUPAMENTOS[agrupar]
    ini = date.fromisoformat(de + "-01")
    fim = _soma_meses(date.fromisoformat(ate + "-01"), 1)   # exclusivo
    if fim <= ini:
        raise HTTPException(400, "O mês final é antes do inicial.")

    fichas = db.execute(text("""
        SELECT id, re, posto_grad, nome, equipe, data_servico, nota, parecer,
               (SELECT count(*) FROM jsonb_each(respostas) e
                 WHERE (e.value->>'conforme')::boolean IS FALSE) AS inconf
          FROM b3.auditoria_cobom
         WHERE data_servico >= :ini AND data_servico < :fim
         ORDER BY data_servico, id
    """), {"ini": ini, "fim": fim}).mappings().all()

    def resumo(lista):
        notas = [f["nota"] for f in lista]
        return {
            "fichas": len(lista),
            "monitorados": len({f["re"] for f in lista}),
            "media": round(sum(notas) / len(notas), 1) if notas else None,
            "min": min(notas) if notas else None,
            "max": max(notas) if notas else None,
            "pareceres": {p: sum(1 for f in lista if f["parecer"] == p) for p in PARECERES},
        }

    # Períodos cobrindo o intervalo, inclusive os sem ficha.
    periodos, p = [], _inicio_periodo(ini, meses)
    while p < fim:
        prox = _soma_meses(p, meses)
        doper = [f for f in fichas if p <= f["data_servico"] < prox]
        periodos.append({"inicio": p, "rotulo": _rotulo_periodo(p, meses), **resumo(doper)})
        p = prox

    # Por PM: todo militar com ficha no intervalo + o efetivo ativo do COBOM.
    efetivo = db.execute(text("""
        SELECT re, posto_grad, nome FROM b1.efetivo WHERE cod_opm_atual = :cobom AND ativo
    """), {"cobom": EM_COBOM}).mappings().all()
    pms = {e["re"]: {"re": e["re"], "posto_grad": e["posto_grad"], "nome": e["nome"],
                     "no_cobom": True} for e in efetivo}
    por_re = {}
    for f in fichas:
        por_re.setdefault(f["re"], []).append(f)
        pms.setdefault(f["re"], {"re": f["re"], "posto_grad": f["posto_grad"],
                                 "nome": f["nome"], "no_cobom": False})

    por_pm = []
    for re_, pm in pms.items():
        lista = por_re.get(re_, [])
        equipes = [f["equipe"] for f in lista if f["equipe"]]
        ult = lista[-1] if lista else None
        por_pm.append({
            **pm, **resumo(lista),
            "equipe": max(set(equipes), key=equipes.count) if equipes else None,
            "inconformidades": sum(f["inconf"] for f in lista),
            "ultima": {"data": ult["data_servico"], "nota": ult["nota"], "id": ult["id"]} if ult else None,
            # Nota média do PM em cada período do gráfico (None = sem ficha).
            "serie": [
                (lambda l: round(sum(x["nota"] for x in l) / len(l), 1) if l else None)(
                    [f for f in lista if per["inicio"] <= f["data_servico"] < _soma_meses(per["inicio"], meses)])
                for per in periodos
            ],
        })
    por_pm.sort(key=lambda m: (m["media"] is None, -(m["media"] or 0), m["nome"]))

    return {
        "agrupar": agrupar, "de": de, "ate": ate,
        "geral": {**resumo(list(fichas)), "efetivo": len(efetivo)},
        "periodos": periodos,
        "por_pm": por_pm,
    }


@router.get("")
def listar(mes: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
           db: Session = Depends(get_db),
           current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    rows = db.execute(text("""
        SELECT a.id, a.re, a.posto_grad, a.nome, a.data_servico, a.turno,
               a.equipe, a.nota, a.parecer, jsonb_array_length(a.audios) AS n_audios,
               (SELECT count(*) FROM jsonb_each(a.respostas) e
                 WHERE (e.value->>'conforme')::boolean IS FALSE) AS n_inconformidades,
               a.avaliador_1
        FROM b3.auditoria_cobom a
        WHERE a.data_servico >= :ini AND a.data_servico < (:ini + interval '1 month')
        ORDER BY a.data_servico DESC, a.id DESC
    """), {"ini": date.fromisoformat(mes + "-01")}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{ficha_id}")
def obter(ficha_id: int, db: Session = Depends(get_db),
          current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    row = db.execute(text("SELECT * FROM b3.auditoria_cobom WHERE id = :id"),
                     {"id": ficha_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Ficha não encontrada")
    return dict(row)


_COLUNAS = ("re, posto_grad, nome, informacao_num, data_servico, turno, equipe, "
            "posto_atendimento, avaliador_1, avaliador_2, audios, respostas, nota, "
            "parecer, observacoes, prov_encarregado, prov_chefe, prov_supervisao")


@router.post("")
def criar(f: Ficha, db: Session = Depends(get_db),
          current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    militar, respostas, audios = _validar(f, db)
    p = _params(f, militar, respostas, audios) | {"uid": current_user.id}
    valores = ", ".join(
        f"CAST(:{c} AS JSONB)" if c in ("audios", "respostas") else f":{c}"
        for c in _COLUNAS.split(", "))
    novo = db.execute(text(f"""
        INSERT INTO b3.auditoria_cobom ({_COLUNAS}, criado_por, atualizado_por)
        VALUES ({valores}, :uid, :uid)
        RETURNING id, nota
    """), p).mappings().first()
    db.commit()
    return dict(novo)


@router.put("/{ficha_id}")
def atualizar(ficha_id: int, f: Ficha, db: Session = Depends(get_db),
              current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    militar, respostas, audios = _validar(f, db)
    p = _params(f, militar, respostas, audios) | {"uid": current_user.id, "id": ficha_id}
    sets = ", ".join(
        f"{c} = CAST(:{c} AS JSONB)" if c in ("audios", "respostas") else f"{c} = :{c}"
        for c in _COLUNAS.split(", "))
    row = db.execute(text(f"""
        UPDATE b3.auditoria_cobom
        SET {sets}, atualizado_por = :uid, atualizado_em = now()
        WHERE id = :id
        RETURNING id, nota
    """), p).mappings().first()
    if not row:
        raise HTTPException(404, "Ficha não encontrada")
    db.commit()
    return dict(row)


@router.delete("/{ficha_id}")
def excluir(ficha_id: int, db: Session = Depends(get_db),
            current_user: Usuario = Depends(get_current_user)):
    check_access(current_user)
    n = db.execute(text("DELETE FROM b3.auditoria_cobom WHERE id = :id"),
                   {"id": ficha_id}).rowcount
    if not n:
        raise HTTPException(404, "Ficha não encontrada")
    db.commit()
    return {"ok": True}
