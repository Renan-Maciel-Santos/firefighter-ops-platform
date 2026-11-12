"""
Consulta de um militar pelo RE — página do B/1 (11/11/2026).

Substitui a lista paginada de todo o efetivo que ficava no fim da aba Pessoal:
o B/1 digita o RE e vê só aquele militar. Saúde (IAS e restrições) e TAF só
vêm para quem já enxerga as abas Saúde e TAF — a consulta não pode virar
atalho para dado que a regra de acesso esconde.
"""
import re as _re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import pode_ver
from efetivo_regras import SQL_PARTE, SQL_OPERACIONAL
from routers.auth import get_current_user
from routers.consulta import buscar_taf, texto_taf

router = APIRouter(prefix="/militar", tags=["militar"])

ABA = "consulta_militar"


@router.get("/{re_txt}")
def consultar(re_txt: str, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not pode_ver(current_user, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Aceita "123456", "123456-7" ou "1234567" (com o dígito colado).
    dig = _re.sub(r"\D", "", re_txt or "")
    if len(dig) == 7:
        dig = dig[:6]
    if not dig:
        raise HTTPException(status_code=400, detail="Informe o RE (só números).")
    re_num = int(dig)

    m = db.execute(text(f"""
        SELECT re, re_dv, nome, posto_grad, quadro, sexo, data_admissao, situacao, ativo,
               opm_atual, opm_efetiva, cod_opm_atual,
               {SQL_PARTE}       AS lotacao,
               {SQL_OPERACIONAL} AS operacional
          FROM b1.efetivo WHERE re = :re
    """), {"re": re_num}).mappings().first()
    if not m:
        raise HTTPException(status_code=404, detail=f"RE {re_num} não encontrado no efetivo.")
    hoje = date.today()
    militar = dict(m)
    if m["data_admissao"]:
        dias = (hoje - m["data_admissao"]).days
        militar["tempo_servico"] = f"{dias // 365} anos e {(dias % 365) // 30} meses"

    contato = db.execute(text("SELECT telefone, cursos FROM b1.contato_militar WHERE re = :re"),
                         {"re": re_num}).mappings().first()
    antig = db.execute(text("""
        SELECT data_promocao_atual, ordem_geral FROM b1.vw_antiguidade WHERE re = :re
    """), {"re": re_num}).mappings().first()

    # Escala de agora (última captura do nível operacional do SIOPM).
    escala = db.execute(text("""
        SELECT v.estacao_nome, v.us, v.status, i.nome_guerra, c.capturado_em
          FROM b3.nivel_op_integrante i
          JOIN b3.nivel_op_viatura v ON v.id = i.viatura_id
          JOIN b3.nivel_op_captura c ON c.id = v.captura_id
         WHERE i.re = :re
           AND c.id = (SELECT id FROM b3.nivel_op_captura ORDER BY capturado_em DESC LIMIT 1)
         LIMIT 1
    """), {"re": re_num}).mappings().first()
    guerra = db.execute(text("""
        SELECT nome_guerra FROM b3.nivel_op_integrante
         WHERE re = :re AND nome_guerra IS NOT NULL ORDER BY id DESC LIMIT 1
    """), {"re": re_num}).scalar()

    afast = db.execute(text("""
        SELECT motivo_grupo AS motivo, data_inicio, data_fim, quantidade_dias, observacao
          FROM b1.v_afastamentos_dedup
         WHERE re = :re
           AND motivo_grupo NOT ILIKE '%PECUNIA%' AND motivo_grupo NOT ILIKE '%SOBREST%'
           AND COALESCE(data_fim, data_inicio) >= :desde
         ORDER BY data_inicio
    """), {"re": re_num, "desde": date(hoje.year - 1, 1, 1)}).mappings().all()
    atuais = [dict(a) for a in afast if a["data_inicio"] <= hoje <= (a["data_fim"] or a["data_inicio"])]
    proximos = [dict(a) for a in afast if a["data_inicio"] > hoje]
    anteriores = [dict(a) for a in afast if (a["data_fim"] or a["data_inicio"]) < hoje][-5:][::-1]

    out = {
        "militar": militar,
        "nome_guerra": guerra,
        "contato": dict(contato) if contato else None,
        "antiguidade": dict(antig) if antig else None,
        "escala_agora": dict(escala) if escala else None,
        "afastamentos": {"atuais": atuais, "proximos": proximos, "anteriores": anteriores},
        "saude": None,
        "taf": None,
    }

    if pode_ver(current_user, "saude"):
        ias = db.execute(text("""
            SELECT data_validade, inspecao_medica, situacao_inspecao FROM b1.ias_inspecao
             WHERE re = :re ORDER BY data_validade DESC NULLS LAST LIMIT 1
        """), {"re": re_num}).mappings().first()
        restricoes = db.execute(text("""
            SELECT origem, restricao_medica, data_inicial, data_final, observacao FROM b1.restricoes
             WHERE re = :re AND (data_final IS NULL OR data_final >= CURRENT_DATE)
               AND observacao != 'Apto Pleno'
             ORDER BY data_inicial DESC
        """), {"re": re_num}).mappings().all()
        if not ias:
            sit = "SEM IAS"
        elif ias["data_validade"] is None:
            sit = "INDETERMINADO"
        elif ias["data_validade"] < hoje:
            sit = "ATRASADA"
        elif (ias["data_validade"] - hoje).days <= 30:
            sit = "EXPIRANDO"
        else:
            sit = "EM DIA"
        out["saude"] = {"ias_situacao": sit, "ias": dict(ias) if ias else None,
                        "restricoes": [dict(r) for r in restricoes]}

    if pode_ver(current_user, "taf"):
        apto, posterior = buscar_taf(db, re_num)
        # texto_taf escreve para o WhatsApp (*negrito*); no painel, sem asterisco.
        out["taf"] = {"situacao": apto["situacao_taf"] if apto else "SEM TAF APTO",
                      "texto": texto_taf(apto, posterior).replace("*", "")}

    return out
