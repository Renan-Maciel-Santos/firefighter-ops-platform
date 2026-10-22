"""
Endpoints públicos consumidos pelo N8N (workflow WhatsApp).
Auth: header X-API-Token vs N8N_TOKEN do .env.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import os, re, sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from efetivo_regras import SQL_PARTE, SQL_OPERACIONAL

# Carrega .env da raiz do projeto (mesma pasta que _comum.py)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

N8N_TOKEN = os.environ.get("N8N_TOKEN", "").strip()

router = APIRouter(prefix="/consulta", tags=["consulta"])


# ---------- Renderização das respostas da B.I.A. ----------
#
# O campo "mensagem" de cada endpoint é o TEXTO FINAL que vai pro WhatsApp,
# já no padrão da casa (emoji + *negrito* + data dd/mm/aaaa). O modelo é
# instruído a repassá-lo literalmente, sem reformatar.
#
# Motivo (medido em 10/08/2026): quando o modelo montava a formatação a
# partir dos dados crus, ele inventava números em ~12% das perguntas —
# inclusive respostas plausíveis como "*0 mergulhadores*". Formatando aqui,
# nenhum número da resposta passa pelo modelo: todos vêm do banco.

EMOJI = {
    "viatura": "🚒", "militar": "👮", "ias": "💊", "restricao": "🩺",
    "taf": "💪", "saude": "❤️", "operacional": "📊", "frota": "🚛",
    "uge": "📁", "elogio": "🎖️",
}


def fmt_data(d) -> str:
    """date/datetime -> dd/mm/aaaa. Devolve '—' quando não houver data."""
    if not d:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except AttributeError:
        return str(d)


def nome_militar(m) -> str:
    """'POSTO NOME' a partir de um registro de b1.efetivo."""
    return f"{m['posto_grad']} {m['nome']}"


# ---------- Auth simples por token estático ----------

def verificar_token(x_api_token: Optional[str] = Header(None)):
    if not N8N_TOKEN:
        raise HTTPException(status_code=503, detail="N8N_TOKEN não configurado no .env")
    if x_api_token != N8N_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")


# ---------- Mapeamento estação → município ----------
#
# As estações do SGP são nomeadas por bairro/localidade, não por município.
# Ex: "PB BOM CONSELHO" está em Taubaté, "EB QUIRIRIM" também.
# Aqui mapeamos substring do nome da estação → município real.
# A busca é case-insensitive e por substring; se surgir estação nova só adicionar.
ESTACAO_MUNICIPIO = {
    # 1º SGB — São José dos Campos e região
    "VILA BETANIA":        "São José dos Campos",
    "VILA BETÂNIA":        "São José dos Campos",
    "VILA INDUSTRIAL":     "São José dos Campos",
    "PB LESTE":            "São José dos Campos",
    "PB SUL":              "São José dos Campos",
    "BB NORTE":            "São José dos Campos",
    "BC PARAIBUNA":        "Paraibuna",
    "PB JACAREI":          "Jacareí",
    "PB JACAREÍ":          "Jacareí",

    # 2º SGB — Taubaté e região
    "PB BOM CONSELHO":     "Taubaté",
    "EB QUIRIRIM":         "Taubaté",
    "PB ANA EMILIA":       "Taubaté",
    "PB ANA EMÍLIA":       "Taubaté",
    "BC SAO LUIZ DO PARAITINGA":  "São Luiz do Paraitinga",
    "BC SÃO LUIZ DO PARAITINGA":  "São Luiz do Paraitinga",
    "PB CACAPAVA":         "Caçapava",
    "PB CAÇAPAVA":         "Caçapava",
    "PB CAMPOS DO JORDAO": "Campos do Jordão",
    "PB CAMPOS DO JORDÃO": "Campos do Jordão",

    # 3º SGB — Guaratinguetá e região
    "EB GUARATINGUETA":    "Guaratinguetá",
    "EB GUARATINGUETÁ":    "Guaratinguetá",
    "EB LORENA":           "Lorena",
    "BC CUNHA":            "Cunha",
    "EB CRUZEIRO":         "Cruzeiro",
    "CACHOEIRA PAULISTA":  "Cachoeira Paulista",
    "BANANAL":             "Bananal",
    "PB PINDAMONHANGABA":  "Pindamonhangaba",
    "EB APARECIDA":        "Aparecida",
    "BC POTIM":            "Potim",
    "BC S. J. DO BARREIRO":"São José do Barreiro",
    "BC S.J. DO BARREIRO": "São José do Barreiro",

    # 4º SGB — Litoral Norte
    "EB CARAGUA":          "Caraguatatuba",
    "EB CARAGUÁ":          "Caraguatatuba",
    "BB UBATUBA":          "Ubatuba",
    "EB SAO SEBASTIAO":    "São Sebastião",
    "EB SÃO SEBASTIÃO":    "São Sebastião",
    "BB ILHABELA":         "Ilhabela",
}


def municipio_de_estacao(nome_estacao_upper: str) -> Optional[str]:
    """Retorna o município mapeado pra uma estação (busca substring, case-insensitive)."""
    if not nome_estacao_upper:
        return None
    up = nome_estacao_upper.upper()
    for chave, mun in ESTACAO_MUNICIPIO.items():
        if chave in up:
            return mun
    return None


def unaccent_upper(s: str) -> str:
    """Normaliza pra comparar sem acento e caixa (útil pra 'taubate' bater 'Taubaté')."""
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode().upper()


def estacoes_do_municipio(municipio_input: str) -> list[str]:
    """Retorna substrings do nome de estação que pertencem ao município consultado."""
    alvo = unaccent_upper(municipio_input)
    encontradas = []
    for chave, mun in ESTACAO_MUNICIPIO.items():
        if unaccent_upper(mun) == alvo:
            encontradas.append(chave)
    return encontradas


# ---------- Parsers dos campos brutos do mapa_forca ----------

# Regex de telefone: aceita "0000-3302", "31058552", "90000-0006", "11900000005"
_RE_TEL_FIXO = re.compile(r"\b(\d{4,5}[-\s]?\d{4})\b")
_RE_TEL_MOVEL = re.compile(r"\b(\d{10,11})\b")


def parse_militar_telefone(raw: Optional[str]) -> dict:
    """
    'OLIVEIRA 11900000004' -> {'nome': 'OLIVEIRA', 'telefone': '11900000004'}
    'FULANO 11900000002'     -> {'nome': 'FULANO', 'telefone': '11900000002'}
    None                   -> {'nome': None, 'telefone': None}
    """
    if not raw:
        return {"nome": None, "telefone": None}

    texto = str(raw).strip()

    # Última sequência de 10-11 dígitos é o celular; o resto é o nome
    m = _RE_TEL_MOVEL.search(texto)
    if m:
        telefone = m.group(1)
        nome = texto[:m.start()].strip() + texto[m.end():].strip()
        return {"nome": nome.strip() or None, "telefone": telefone}

    return {"nome": texto, "telefone": None}


def parse_estacao(raw: Optional[str]) -> dict:
    """
    '990113302\\nEB APARECIDA\\n0000-3302' -> {'codigo_opm': '990113302', 'nome': 'EB APARECIDA', 'telefone_quartel': '0000-3302'}
    '990112201 PB ANA EMILIA 0000-2201'    -> {'codigo_opm': '990112201', 'nome': 'PB ANA EMILIA', 'telefone_quartel': '0000-2201'}
    'BB NORTE'                              -> {'codigo_opm': None, 'nome': 'BB NORTE', 'telefone_quartel': None}
    """
    if not raw:
        return {"codigo_opm": None, "nome": None, "telefone_quartel": None}

    # Normaliza whitespace (troca \n por espaço, colapsa espaços)
    texto = re.sub(r"\s+", " ", str(raw)).strip()

    codigo_opm = None
    telefone = None

    # Código OPM: primeira sequência de 8-9 dígitos no começo
    m_opm = re.match(r"^(\d{8,9})\s+", texto)
    if m_opm:
        codigo_opm = m_opm.group(1)
        texto = texto[m_opm.end():].strip()

    # Telefone: última ocorrência (fixo XXXX-XXXX ou XXXXX-XXXX ou móvel 11 dígitos)
    m_tel = None
    for m in _RE_TEL_FIXO.finditer(texto):
        m_tel = m
    for m in _RE_TEL_MOVEL.finditer(texto):
        m_tel = m

    if m_tel:
        telefone = m_tel.group(1)
        # Remove o telefone da string pro nome ficar limpo
        texto = (texto[:m_tel.start()] + texto[m_tel.end():]).strip()

    nome_estacao = texto.strip() or None
    return {
        "codigo_opm": codigo_opm,
        "nome": nome_estacao,
        "municipio": municipio_de_estacao(nome_estacao) if nome_estacao else None,
        "telefone_quartel": telefone,
    }


# ---------- Endpoint principal ----------

@router.get("/guarnicao")
def consultar_guarnicao(
    _=Depends(verificar_token),
    estacao: Optional[str] = Query(None, description="Nome ou parte do nome da estação (ex: 'aparecida', 'ana emilia')"),
    municipio: Optional[str] = Query(None, description="Município do Vale (ex: 'Taubaté', 'Guaratinguetá', 'São Sebastião')"),
    viatura: Optional[str] = Query(None, description="Prefixo/tipo de viatura (ex: 'AB', 'ABS', 'UR-11208')"),
    db: Session = Depends(get_db),
):
    """
    Retorna a(s) guarnição(ões) do último snapshot do Mapa de Força que casam com os filtros.

    Pelo menos um filtro entre 'estacao' e 'municipio' precisa ser passado.
    - 'municipio' expande pra todas as estações mapeadas nele (ex: Taubaté → BOM CONSELHO, QUIRIRIM, ANA EMILIA).
    - Se a viatura está OPERANDO: retorna o Cmt (nome, posto, telefone) + estação + município.
    - Se está RESERVA/BAIXADA: retorna 'sem guarnição hoje' + telefone do quartel.
    - Se nada bater os filtros: 404.
    """

    if not estacao and not municipio:
        raise HTTPException(status_code=400, detail="Informe pelo menos 'estacao' ou 'municipio'")

    sid = db.execute(text(
        "SELECT id FROM b3.mapa_forca_snapshot_raw "
        "ORDER BY data_servico DESC NULLS LAST, capturado_em DESC LIMIT 1"
    )).scalar()

    if not sid:
        raise HTTPException(status_code=404, detail="Nenhum snapshot do Mapa de Força disponível")

    filtros = ["l.snapshot_id = :sid"]
    params: dict = {"sid": sid}

    if estacao:
        filtros.append("(l.estacao_bombeiros ILIKE :estacao OR e.estacao_nome ILIKE :estacao)")
        params["estacao"] = f"%{estacao}%"

    if municipio:
        # Acima: Expande município → OR de todas as estações mapeadas
        substrings = estacoes_do_municipio(municipio)
        if not substrings:
            raise HTTPException(
                status_code=404,
                detail=f"Município '{municipio}' não tem estações mapeadas (adicione em ESTACAO_MUNICIPIO)",
            )
        # Constrói (estacao_bombeiros ILIKE :m0 OR ... OR ILIKE :mN)
        or_clauses = []
        for i, sub in enumerate(substrings):
            key = f"m{i}"
            or_clauses.append(f"(l.estacao_bombeiros ILIKE :{key} OR e.estacao_nome ILIKE :{key})")
            params[key] = f"%{sub}%"
        filtros.append("(" + " OR ".join(or_clauses) + ")")

    if viatura:
        filtros.append("l.viatura ILIKE :viatura")
        params["viatura"] = f"%{viatura}%"

    where = " AND ".join(filtros)
    rows = db.execute(text(f"""
        SELECT l.bloco_nome, l.estacao_bombeiros, l.viatura, l.situacao,
               l.posto_graduacao, l.militar_e_telefone,
               e.estacao_nome, e.estacao_codigo, e.estacao_telefone
        FROM b3.mapa_forca_linha l
        LEFT JOIN b3.mapa_forca_estacao e ON e.id = l.estacao_id
        WHERE {where}
        ORDER BY l.viatura
    """), params).mappings().all()

    if not rows:
        partes = []
        if estacao:   partes.append(f"estação~'{estacao}'")
        if municipio: partes.append(f"município='{municipio}'")
        if viatura:   partes.append(f"viatura~'{viatura}'")
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma viatura encontrada com {' + '.join(partes)}",
        )

    resultado = []
    for r in rows:
        # Snapshots novos já trazem a estação normalizada (nome, código e
        # telefone em colunas próprias); os antigos ainda dependem do parse
        # do texto bruto, que misturava os três na mesma célula.
        if r["estacao_nome"]:
            est = {
                "codigo_opm": r["estacao_codigo"],
                "nome": r["estacao_nome"],
                "municipio": municipio_de_estacao(r["estacao_nome"]),
                "telefone_quartel": r["estacao_telefone"],
            }
        else:
            est = parse_estacao(r["estacao_bombeiros"])

        situacao = r["situacao"]

        item = {
            "sgb": r["bloco_nome"],
            "estacao": est,
            "viatura": r["viatura"],
            "situacao": situacao,
        }

        if situacao == "OPERANDO":
            mil = parse_militar_telefone(r["militar_e_telefone"])
            item["guarnicao"] = {
                "posto": r["posto_graduacao"],
                "nome": mil["nome"],
                "telefone": mil["telefone"],
            }
            item["mensagem"] = f'Cmt da guarnição atual: {r["posto_graduacao"]} {mil["nome"]} — {mil["telefone"] or "sem telefone"}'
        else:
            item["guarnicao"] = None
            item["mensagem"] = f"Viatura {situacao} — sem guarnição hoje. Ligue no quartel: {est['telefone_quartel'] or 'telefone não cadastrado'}"

        resultado.append(item)

    # Texto final pro WhatsApp, uma viatura por bloco.
    blocos = []
    for it in resultado:
        est = it["estacao"]
        cabec = f"{EMOJI['viatura']} *{it['viatura']}* — {est['nome']} ({est['municipio'] or '—'})"
        if it["guarnicao"]:
            g = it["guarnicao"]
            blocos.append(
                f"{cabec}\n{EMOJI['militar']} {g['posto']} {g['nome']}"
                f"\n📞 {g['telefone'] or 'sem telefone'}"
            )
        else:
            blocos.append(
                f"{cabec}\n⚠️ *{it['situacao']}* — sem guarnição hoje"
                f"\n📞 quartel: {est['telefone_quartel'] or 'não cadastrado'}"
            )

    return {
        "total": len(resultado),
        "data": resultado,
        "mensagem": "\n\n".join(blocos),
    }


# ==========================================================================
# TOOLS ADICIONAIS PRO AI AGENT
# Cada endpoint é pensado pra ser chamado como "tool" pelo LLM.
# Auth continua sendo X-API-Token.
# ==========================================================================


@router.get("/militar")
def consultar_militar(
    _=Depends(verificar_token),
    re: Optional[int] = Query(None, description="RE do militar (número, sem hífen)"),
    nome: Optional[str] = Query(None, description="Parte do nome (fuzzy)"),
    db: Session = Depends(get_db),
):
    """
    Busca dados de um militar por RE ou por parte do nome.
    Retorna posto, nome completo, OPM, situação, ativo/inativo.
    Se buscar por nome, pode retornar múltiplos resultados (limite 20).
    """
    if not re and not nome:
        raise HTTPException(status_code=400, detail="Informe 're' ou 'nome'")

    filtros = []
    params: dict = {}
    if re:
        filtros.append("re = :re")
        params["re"] = re
    if nome:
        filtros.append("nome ILIKE :nome")
        params["nome"] = f"%{nome}%"

    where = " AND ".join(filtros)
    rows = db.execute(text(f"""
        SELECT re, nome, posto_grad, quadro, sexo, data_admissao,
               opm_atual, opm_efetiva, situacao, ativo
        FROM b1.efetivo
        WHERE {where}
        ORDER BY ativo DESC, nome
        LIMIT 20
    """), params).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Nenhum militar encontrado (re={re}, nome={nome!r})")

    # Enriquece cada registro com status_atual EXPLÍCITO — evita LLM ler "opm_atual=11.GB"
    # + "situacao=EFETIVO" e concluir erroneamente que militar inativo ainda está na unidade.
    resultado = []
    for r in rows:
        d = dict(r)
        if d["ativo"]:
            d["status_atual"] = f"ATIVO no {d['opm_atual']}"
        else:
            # Redigido como FATO, não como ordem ao modelo: se ele copiar
            # este texto na resposta, o Comandante lê algo coerente em vez
            # de instrução interna (o modelo às vezes repete o texto da ferramenta).
            d["status_atual"] = (
                f"⚠️ INATIVO / TRANSFERIDO — não faz mais parte do 11º GB. "
                f"Última lotação registrada: {d['opm_atual']}."
            )
        resultado.append(d)

    linhas = []
    for d in resultado:
        if d["ativo"]:
            linhas.append(
                f"{EMOJI['militar']} {d['posto_grad']} {d['nome']} (RE {d['re']})"
                f"\n📍 *ATIVO* — {d['opm_atual']}"
            )
        else:
            linhas.append(
                f"{EMOJI['militar']} {d['posto_grad']} {d['nome']} (RE {d['re']})"
                f"\n⚠️ *INATIVO / TRANSFERIDO* — não faz mais parte do 11º GB."
                f"\nÚltima lotação: {d['opm_atual']}"
            )

    return {
        "total": len(resultado),
        "data": resultado,
        "mensagem": "\n\n".join(linhas),
    }


@router.get("/ias")
def consultar_ias(
    _=Depends(verificar_token),
    re: int = Query(..., description="RE do militar"),
    db: Session = Depends(get_db),
):
    """
    Retorna a inspeção anual (IAS) mais recente do militar + situação (em dia, atrasada, expirando).
    Se não encontrar, indica que o militar está SEM IAS.
    """
    militar = db.execute(text("""
        SELECT re, nome, posto_grad FROM b1.efetivo WHERE re = :re
    """), {"re": re}).mappings().first()

    if not militar:
        raise HTTPException(status_code=404, detail=f"Militar RE={re} não encontrado no efetivo")

    ias = db.execute(text("""
        SELECT ano, numero_processo,
               data_inspecao_medica, data_inspecao_odontologica, data_validade,
               inspecao_medica, inspecao_odontologica,
               parecer_medico_taf, parecer_medico_tat, situacao_inspecao
        FROM b1.ias_inspecao
        WHERE re = :re
        ORDER BY data_validade DESC NULLS LAST
        LIMIT 1
    """), {"re": re}).mappings().first()

    resultado = {"militar": dict(militar)}

    if not ias:
        resultado["ias"] = None
        resultado["situacao"] = "SEM IAS"
        resultado["mensagem"] = (
            f"{EMOJI['ias']} {nome_militar(militar)} (RE {militar['re']}): *SEM IAS* registrada."
        )
        return resultado

    ias_dict = dict(ias)
    validade = ias_dict.get("data_validade")

    # Situação prática (usa a mesma lógica das views b1.vw_ias_*)
    if validade is None:
        situacao = "INDETERMINADO"
    else:
        from datetime import date
        hoje = date.today()
        if validade < hoje:
            situacao = "ATRASADA"
        elif (validade - hoje).days <= 30:
            situacao = "EXPIRANDO"
        else:
            situacao = "EM DIA"

    resultado["ias"] = ias_dict
    resultado["situacao"] = situacao
    resultado["mensagem"] = (
        f"{EMOJI['ias']} {nome_militar(militar)} (RE {militar['re']}): "
        f"*IAS {situacao}* — validade {fmt_data(validade)}."
    )
    return resultado


@router.get("/restricoes")
def consultar_restricoes_militar(
    _=Depends(verificar_token),
    re: int = Query(..., description="RE do militar"),
    db: Session = Depends(get_db),
):
    """
    Retorna as restrições VIGENTES (data_final >= hoje ou NULL) de um militar.
    Se nada estiver vigente, informa 'sem restrições vigentes'.
    """
    militar = db.execute(text("""
        SELECT re, nome, posto_grad FROM b1.efetivo WHERE re = :re
    """), {"re": re}).mappings().first()

    if not militar:
        raise HTTPException(status_code=404, detail=f"Militar RE={re} não encontrado no efetivo")

    restricoes = db.execute(text("""
        SELECT origem, restricao_medica, data_inicial, data_final, total_dias, observacao, condicao
        FROM b1.restricoes
        WHERE re = :re
          AND (data_final IS NULL OR data_final >= CURRENT_DATE)
          AND observacao != 'Apto Pleno'
        ORDER BY data_inicial DESC
    """), {"re": re}).mappings().all()

    resultado = {"militar": dict(militar), "total": len(restricoes), "restricoes": [dict(r) for r in restricoes]}

    if not restricoes:
        resultado["mensagem"] = (
            f"{EMOJI['restricao']} {nome_militar(militar)} (RE {militar['re']}): "
            f"*SEM restrições vigentes* hoje."
        )
    else:
        origens = ", ".join(sorted({r["origem"] for r in restricoes if r["origem"]}))
        detalhe = "\n".join(
            f"• {r['origem'] or 'não informado'} — até {fmt_data(r['data_final'])}"
            for r in restricoes
        )
        resultado["mensagem"] = (
            f"{EMOJI['restricao']} {nome_militar(militar)} (RE {militar['re']}): "
            f"*{len(restricoes)} restrição(ões) vigente(s)*\n{detalhe}"
        )
    return resultado


def buscar_taf(db: Session, re: int):
    """
    Situação do TAF pela mesma regra do painel (B1/migra_taf_exige_apto.sql):
    vale o último Apto, qualquer que seja o status. Devolve (apto, posterior):
    `posterior` é um Inapto/Ausente finalizado depois desse Apto — não muda a
    situação, mas o Comandante precisa saber que o último teste não foi Apto.
    """
    apto = db.execute(text("""
        SELECT tipo_taf, resultado, status, data_realizado, valido_ate, situacao_taf
        FROM b1.vw_taf_ultimo_apto_por_re
        WHERE re = :re
    """), {"re": re}).mappings().first()

    posterior = db.execute(text("""
        SELECT resultado, data_realizado
        FROM b1.taf_resultados_raw
        WHERE re = :re
          AND status = 'Finalizado'
          AND resultado IN ('Inapto', 'Ausente')
          AND data_realizado > COALESCE(:desde, DATE '1900-01-01')
        ORDER BY data_realizado DESC
        LIMIT 1
    """), {"re": re, "desde": apto["data_realizado"] if apto else None}).mappings().first()

    return apto, posterior


def texto_taf(apto, posterior) -> str:
    """Trecho da resposta sobre o TAF, sem o nome do militar."""
    if not apto:
        texto = "*SEM TAF Apto* registrado"
    else:
        # tipo_taf vem nulo em parte dos registros antigos — omite em vez de
        # escrever "None" na resposta que vai pro Comandante.
        tipo = f" ({apto['tipo_taf']})" if apto["tipo_taf"] else ""
        if apto["situacao_taf"] == "VÁLIDO":
            texto = (
                f"*VÁLIDO* — Apto{tipo} em {fmt_data(apto['data_realizado'])},"
                f" vale até {fmt_data(apto['valido_ate'])}"
            )
            if apto["status"] != "Finalizado":
                texto += " (aguardando homologação)"
        else:
            texto = (
                f"*VENCIDO* — último Apto{tipo} em {fmt_data(apto['data_realizado'])},"
                f" venceu em {fmt_data(apto['valido_ate'])}"
            )
    if posterior:
        texto += (
            f"\n   ⚠️ Último TAF finalizado: *{posterior['resultado']}*"
            f" em {fmt_data(posterior['data_realizado'])}"
        )
    return texto


@router.get("/taf")
def consultar_taf(
    _=Depends(verificar_token),
    re: int = Query(..., description="RE do militar"),
    db: Session = Depends(get_db),
):
    """
    Retorna a situação do TAF (Teste de Aptidão Física) do militar — VÁLIDO,
    VENCIDO ou SEM TAF —, pela mesma regra do painel.
    """
    militar = db.execute(text("""
        SELECT re, nome, posto_grad FROM b1.efetivo WHERE re = :re
    """), {"re": re}).mappings().first()

    if not militar:
        raise HTTPException(status_code=404, detail=f"Militar RE={re} não encontrado no efetivo")

    apto, posterior = buscar_taf(db, re)
    return {
        "militar": dict(militar),
        "taf": dict(apto) if apto else None,
        "ultimo_nao_apto": dict(posterior) if posterior else None,
        "mensagem": (
            f"{EMOJI['taf']} {nome_militar(militar)} (RE {militar['re']}): "
            f"{'TAF ' if apto else ''}{texto_taf(apto, posterior)}."
        ),
    }


@router.get("/saude-geral")
def consultar_saude_geral(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """
    Resumo geral de saúde do 11º GB: quantos militares com IAS em dia / atrasada / sem IAS,
    e quantos com restrições médicas vigentes.
    Números agregados, ideal pra dar overview no WhatsApp.
    """
    ias = db.execute(text("""
        SELECT situacao_ias, quantidade, percentual
        FROM b1.vw_ias_percentual
        ORDER BY CASE situacao_ias WHEN 'EM DIA' THEN 1 WHEN 'ATRASADA' THEN 2 WHEN 'SEM IAS' THEN 3 ELSE 99 END
    """)).mappings().all()

    restricoes_vigentes = db.execute(text("""
        SELECT COUNT(DISTINCT r.re) AS qtd
        FROM b1.restricoes r
        JOIN b1.efetivo e ON e.re = r.re AND e.ativo = true
        WHERE r.observacao != 'Apto Pleno'
          AND (r.data_final IS NULL OR r.data_final >= CURRENT_DATE)
    """)).scalar()

    total_ativo = db.execute(text("SELECT COUNT(*) FROM b1.efetivo WHERE ativo = true")).scalar()

    partes = [f"{r['quantidade']} {r['situacao_ias']} ({r['percentual']}%)" for r in ias]
    mensagem = (
        f"{EMOJI['saude']} *{total_ativo} ativos*: "
        + " • ".join(partes)
        + f" • {restricoes_vigentes} com restrição vigente."
    )
    return {
        "total_ativos": total_ativo,
        "ias": [dict(r) for r in ias],
        "restricoes_vigentes": restricoes_vigentes,
        "mensagem": mensagem,
    }


@router.get("/efetivo-por-lotacao")
def consultar_efetivo_por_lotacao(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """
    Quantitativo de militares ativos por SGB / lotação (EM, 1º SGB, 2º SGB, 3º SGB, 4º SGB).
    Útil pra saber quantos estão em cada unidade.
    """
    rows = db.execute(text("""
        SELECT lotacao, COUNT(*) AS quantidade
        FROM b1.vw_efetivo_classificado
        WHERE ativo = true
        GROUP BY lotacao
        ORDER BY lotacao
    """)).mappings().all()

    total = sum(r["quantidade"] for r in rows)
    partes = [f"{r['lotacao']}: {r['quantidade']}" for r in rows]
    mensagem = f"Efetivo por lotação ({total} ativos): " + " • ".join(partes)

    return {
        "total": total,
        "por_lotacao": [dict(r) for r in rows],
        "mensagem": mensagem,
    }


@router.get("/identificar")
def identificar_remetente(
    _=Depends(verificar_token),
    telefone: str = Query(..., description="Número do WhatsApp (com ou sem DDI/DDD, com ou sem hífens)"),
    db: Session = Depends(get_db),
):
    """
    Identifica o remetente pelo número do WhatsApp. Usa a tabela bia.contatos_autorizados.
    Retorna posto, nome curto, apelido, papel (Cmt Geral, Subcmt, Oficial, Praça).
    Se não encontrar, 'conhecido' vem False e 'mensagem' já traz a negação de acesso
    pronta — a B.I.A. não libera as demais tools nesse caso.
    """
    # Normaliza o telefone: só dígitos, tenta com/sem DDI 55
    import re as regex
    digitos = regex.sub(r"\D", "", telefone)
    if digitos.startswith("55") and len(digitos) > 11:
        digitos_alt = digitos[2:]
    else:
        digitos_alt = "55" + digitos

    contato = db.execute(text("""
        SELECT telefone, re, posto_abrev, nome_curto, apelido, papel, observacao
        FROM bia.contatos_autorizados
        WHERE telefone = :t1 OR telefone = :t2
        LIMIT 1
    """), {"t1": digitos, "t2": digitos_alt}).mappings().first()

    if not contato:
        # 'mensagem' é o ÚNICO campo que a B.I.A. repassa ao Comandante, literalmente
        # (regra "FORMATO DA RESPOSTA" do system prompt). Então ele precisa conter o
        # texto final, nunca instrução pro agente — senão a instrução vaza pro WhatsApp.
        # O texto abaixo é o mesmo da regra de negação do prompt, montado aqui pra o
        # modelo não precisar redigitar o número (foi assim que ele duplicou um dígito
        # em 26/08/2026 e negou acesso a quem estava na whitelist).
        return {
            "conhecido": False,
            "telefone_normalizado": digitos,
            "mensagem": (
                f"Comandante, seu número (+{digitos}) não consta na lista de "
                "autorizados. Solicite acesso ao Cmt do 11º GB."
            ),
        }

    c = dict(contato)
    forma_tratamento = c["apelido"] or f"{c['posto_abrev']} {c['nome_curto']}"
    return {
        "conhecido": True,
        "telefone": c["telefone"],
        "re": c["re"],
        "posto_abrev": c["posto_abrev"],
        "nome_curto": c["nome_curto"],
        "apelido": c["apelido"],
        "papel": c["papel"],
        "observacao": c["observacao"],
        "forma_tratamento": forma_tratamento,
        # Antes este campo trazia "Identificado: FULANO (Praca). Trate como 'X'." — uma
        # orientação interna. Como o prompt manda repassar 'mensagem' sem mudar uma
        # vírgula, a B.I.A. respondia a saudação E o texto que dizia como tratá-lo.
        # O que o Comandante deve ler é só a saudação; o resto já vai nos campos acima,
        # que o prompt classifica como contexto.
        "mensagem": f"Às ordens, {forma_tratamento}.",
    }


# ==========================================================================
# CROSS-DOMAIN QUERIES — cruzam efetivo + saúde/TAF/restrições
# Cada endpoint responde a uma pergunta que hoje exigiria 3 consultas manuais.
# ==========================================================================


@router.get("/ias-por-sgb")
def consultar_ias_por_sgb(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """
    Distribuição da situação da IAS por SGB (lotação): quantos EM DIA / ATRASADA / SEM IAS.
    Mostra onde o problema de IAS está concentrado.
    """
    rows = db.execute(text("""
        WITH ias_status AS (
            SELECT
                e.re,
                e.lotacao,
                CASE
                    WHEN i.data_validade IS NULL                THEN 'SEM IAS'
                    WHEN i.data_validade < CURRENT_DATE         THEN 'ATRASADA'
                    WHEN i.data_validade <= CURRENT_DATE + 30   THEN 'EXPIRANDO'
                    ELSE 'EM DIA'
                END AS situacao
            FROM b1.vw_efetivo_classificado e
            LEFT JOIN LATERAL (
                SELECT data_validade FROM b1.ias_inspecao
                WHERE re = e.re ORDER BY data_validade DESC NULLS LAST LIMIT 1
            ) i ON true
            WHERE e.ativo = true
        )
        SELECT lotacao, situacao, COUNT(*) AS quantidade
        FROM ias_status
        GROUP BY lotacao, situacao
        ORDER BY lotacao, situacao
    """)).mappings().all()

    # Pivota pra formato mais amigável
    por_sgb = {}
    for r in rows:
        lot = r["lotacao"]
        if lot not in por_sgb:
            por_sgb[lot] = {"lotacao": lot, "EM DIA": 0, "EXPIRANDO": 0, "ATRASADA": 0, "SEM IAS": 0, "total": 0}
        por_sgb[lot][r["situacao"]] = r["quantidade"]
        por_sgb[lot]["total"] += r["quantidade"]

    lista = sorted(por_sgb.values(), key=lambda x: x["lotacao"])

    partes = [
        f"{x['lotacao']}: {x['ATRASADA']} atrasadas, {x['SEM IAS']} sem IAS ({x['total']} militares)"
        for x in lista
    ]
    mensagem = "IAS por SGB — " + " | ".join(partes)
    return {"por_sgb": lista, "mensagem": mensagem}


@router.get("/efetivo-disponivel-por-sgb")
def consultar_efetivo_disponivel_por_sgb(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """
    Efetivo REAL disponível por SGB: ativos - militares com restrição vigente ou LTS.
    Métrica-chave pra o Comandante saber quem efetivamente pode subir viatura.
    """
    rows = db.execute(text("""
        WITH indisponivel AS (
            SELECT DISTINCT r.re
            FROM b1.restricoes r
            JOIN b1.efetivo e ON e.re = r.re AND e.ativo = true
            WHERE r.observacao != 'Apto Pleno'
              AND (r.data_final IS NULL OR r.data_final >= CURRENT_DATE)
        )
        SELECT
            e.lotacao,
            COUNT(*)                                        AS ativos,
            COUNT(*) FILTER (WHERE i.re IS NOT NULL)        AS indisponiveis,
            COUNT(*) - COUNT(*) FILTER (WHERE i.re IS NOT NULL) AS disponiveis
        FROM b1.vw_efetivo_classificado e
        LEFT JOIN indisponivel i ON i.re = e.re
        WHERE e.ativo = true
        GROUP BY e.lotacao
        ORDER BY e.lotacao
    """)).mappings().all()

    lista = [dict(r) for r in rows]
    total_ativos = sum(x["ativos"] for x in lista)
    total_indisp = sum(x["indisponiveis"] for x in lista)
    total_disp   = sum(x["disponiveis"] for x in lista)

    partes = [f"{x['lotacao']}: {x['disponiveis']}/{x['ativos']}" for x in lista]
    # "Apto", e não "disponível": existe outra rota, /consulta/efetivo-operacional-
    # disponivel, que responde o quantitativo da tropa. Enquanto as duas se
    # chamassem "disponível", nem o modelo nem quem lê a resposta distinguia —
    # em 09/09/2026 a B.I.A. respondeu esta aqui a uma pergunta de efetivo
    # operacional, e o texto não denunciava a troca.
    mensagem = (
        f"Efetivo apto ao serviço por SGB, por saúde (apto/total ativo): "
        + " • ".join(partes)
        + f" • TOTAL: {total_disp}/{total_ativos} ({total_indisp} inaptos por restrição/LTS)"
    )
    return {
        "total_ativos": total_ativos,
        "total_indisponiveis": total_indisp,
        "total_disponiveis": total_disp,
        "por_sgb": lista,
        "mensagem": mensagem,
    }


@router.get("/efetivo-operacional-disponivel")
def consultar_efetivo_operacional_disponivel(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """
    Quantitativo de efetivo OPERACIONAL disponível, por lotação.

    NÃO confundir com /consulta/efetivo-disponivel-por-sgb, que responde outra
    pergunta: lá "disponível" é ativo sem restrição médica nem LTS — é leitura
    de saúde. Aqui é quem está lotado em unidade operacional (cod_opm que não
    termina em zero) e não está fora do serviço por situação (LSV, candidato a
    cargo eletivo, licença junto a organização civil).

    Férias e licença-prêmio NÃO descontam: são ausências rotativas e previstas,
    e o quantitativo que interessa ao Comando é o da tropa, não o do dia
    (decisão do Cmt em 09/09/2026). Ver B1/migra_efetivo_disponivel.sql.
    """
    rows = db.execute(text(
        "SELECT * FROM b1.vw_efetivo_disponivel"
    )).mappings().all()

    lista = [dict(r) for r in rows if r["lotacao"] != "TOTAL GERAL"]
    total = next((dict(r) for r in rows if r["lotacao"] == "TOTAL GERAL"), None)

    # Frescor: a captura do SGP roda de hora em hora, mas já parou por dias.
    # O prompt da B.I.A. manda respeitar este campo em vez de dizer "hoje" por
    # achismo — sem ele, dado velho sai com cara de dado novo.
    fresco = db.execute(text("""
        SELECT EXTRACT(EPOCH FROM (now() - COALESCE(finalizado_em, iniciado_em))) / 3600
          FROM b1.etl_status
         WHERE dominio = 'efetivo'
    """)).scalar()

    if fresco is None:
        frescor_texto = "sem registro de atualização"
    elif fresco < 2:
        frescor_texto = "atualizado agora"
    elif fresco < 24:
        frescor_texto = f"atualizado há {int(fresco)}h"
    else:
        frescor_texto = f"atualizado há {int(fresco // 24)} dias"

    partes = [f"{x['lotacao']}: {x['disponivel']}/{x['operacional']}" for x in lista]
    fora = total["fora_do_servico"] if total else 0

    mensagem = (
        f"Efetivo operacional disponível ({frescor_texto}) "
        f"[disponível/lotado em unidade operacional]: "
        + " • ".join(partes)
        + (f" • TOTAL: {total['disponivel']}/{total['operacional']}" if total else "")
        + (f" • {fora} fora do serviço (LSV, candidato, licença em org. civil)"
           if fora else "")
        + " • Férias e licença-prêmio não descontam."
    )

    return {
        "frescor": frescor_texto,
        "total_operacional": total["operacional"] if total else None,
        "total_disponivel": total["disponivel"] if total else None,
        "total_fora_do_servico": fora,
        "por_lotacao": lista,
        "mensagem": mensagem,
    }


# Sinônimos que o Comando usa para cada lotação. A B.I.A. recebe linguagem
# livre — "no 2º SGB", "do segundo", "na sede" — e o parâmetro tem de aceitar
# tudo isso sem obrigar ninguém a decorar a grafia do banco ("2°Sgb").
_APELIDOS_LOTACAO = {
    "1°Sgb": ["1", "1º", "1°", "1o", "primeiro", "1 sgb", "1ºsgb"],
    "2°Sgb": ["2", "2º", "2°", "2o", "segundo", "2 sgb", "2ºsgb"],
    "3°Sgb": ["3", "3º", "3°", "3o", "terceiro", "3 sgb", "3ºsgb"],
    "4°Sgb": ["4", "4º", "4°", "4o", "quarto", "4 sgb", "4ºsgb"],
    "EM":    ["em", "sede", "estado maior", "estado-maior", "cmdo", "comando"],
}


def _resolver_lotacao(texto):
    """Texto livre -> chave da lotação, ou None se não reconhecer."""
    if not texto:
        return None
    t = texto.strip().lower()
    t = re.sub(r"[°º]", "", t)
    t = re.sub(r"\bsgb\b", "", t).strip()
    for chave, apelidos in _APELIDOS_LOTACAO.items():
        alvo = re.sub(r"[°º]", "", chave.lower()).replace("sgb", "").strip()
        if t == alvo:
            return chave
        for a in apelidos:
            if t == re.sub(r"[°º]", "", a).replace("sgb", "").strip():
                return chave
    return None


@router.get("/efetivo")
def consultar_efetivo(
    _=Depends(verificar_token),
    lotacao: Optional[str] = Query(None, description="1 a 4, ou EM. Vazio = todas."),
    db: Session = Depends(get_db),
):
    """Retrato do efetivo: quantos são, quantos estão aptos, quantos na atividade-fim.

    Substitui três consultas que se sobrepunham e competiam entre si
    (efetivo-por-lotacao, efetivo-disponivel-por-sgb e
    efetivo-operacional-disponivel). Em 09/09/2026 a B.I.A. respondeu duas
    vezes a pergunta errada porque as três tinham nome parecido e o modelo
    escolhia pelo nome. Uma consulta só não tem como ser escolhida errado.

    Os três números são recortes DIFERENTES do mesmo total, não uma subtração
    em cadeia: 'apto' é leitura de saúde, 'atividade-fim' é de lotação. Por
    isso cada linha da resposta explica a própria conta.
    """
    # Lotação e atividade-fim vêm de efetivo_regras.py, a mesma regra do card do
    # painel, para a B.I.A. dar o MESMO número que ele. Isso inclui a SAT: os
    # NATs dos SGBs (99011x900) contam no EM, e os Subten/Sgt dela na
    # atividade-fim. Sem isso o EM sairia 80/36 aqui e 88/43 lá.
    linhas = db.execute(text(f"""
        WITH pessoa AS (
            SELECT
                e.re,
                {SQL_PARTE}                                     AS parte,
                {SQL_OPERACIONAL}                               AS atividade_fim,
                COALESCE(e.situacao, '') <> 'EFETIVO'            AS licenca_longa,
                EXISTS (
                    SELECT 1 FROM b1.restricoes r
                     WHERE r.re = e.re
                       AND r.observacao <> 'Apto Pleno'
                       AND (r.data_final IS NULL OR r.data_final >= CURRENT_DATE)
                )                                               AS com_restricao
              FROM b1.efetivo e
             WHERE e.ativo = true
        )
        SELECT CASE WHEN parte IN ('SAT','COBOM','ADM') THEN 'EM' ELSE parte END AS lotacao,
               CASE WHEN parte IN ('SAT','COBOM','ADM') THEN 1
                    WHEN parte = '1°Sgb' THEN 2
                    WHEN parte = '2°Sgb' THEN 3
                    WHEN parte = '3°Sgb' THEN 4
                    WHEN parte = '4°Sgb' THEN 5
                    ELSE 99 END                                      AS ord,
               count(*)                                             AS efetivo,
               count(*) FILTER (WHERE NOT com_restricao)             AS aptos,
               count(*) FILTER (WHERE com_restricao)                 AS restritos,
               count(*) FILTER (WHERE atividade_fim)                 AS fim,
               count(*) FILTER (WHERE NOT atividade_fim)             AS administrativo,
               count(*) FILTER (WHERE licenca_longa)                 AS licenca
          FROM pessoa
         GROUP BY 1, 2
         ORDER BY 2
    """)).mappings().all()

    dados = [dict(r) for r in linhas]
    alvo = _resolver_lotacao(lotacao)

    if lotacao and not alvo:
        return {"mensagem": f"Comandante, não reconheci a lotação '{lotacao}'. "
                            f"Use 1, 2, 3, 4 ou EM."}

    def bonito(chave):
        """'2°Sgb' -> '2º SGB'. O rótulo do banco não vai para o Comandante."""
        return "EM" if chave == "EM" else chave.replace("°Sgb", "º SGB")

    def bloco(d, titulo):
        # Duas leituras do MESMO total, cada uma fechando sozinha:
        #   aptos + restritos      = efetivo   (leitura de saúde)
        #   fim   + administrativo = efetivo   (leitura de lotação)
        # Não são etapas de uma subtração em cadeia, e a resposta não pode
        # sugerir que sejam.
        partes = [f"*{titulo}* — {d['efetivo']} militares"]
        partes.append(
            f"• {d['aptos']} aptos ao serviço"
            + (f" · {d['restritos']} com restrição ou LTS" if d["restritos"] else "")
        )
        partes.append(
            f"• {d['fim']} na atividade-fim"
            + (f" · {d['administrativo']} em função administrativa"
               if d["administrativo"] else "")
        )
        if d["licenca"]:
            partes.append(f"Fora do serviço: {d['licenca']} em licença longa "
                          f"(LSV, cargo eletivo, organização civil)")
        return "\n".join(partes)

    if alvo:
        d = next((x for x in dados if x["lotacao"] == alvo), None)
        if not d:
            return {"mensagem": f"Comandante, não há efetivo registrado em {alvo}."}
        return {"lotacao": alvo, "detalhe": d, "mensagem": bloco(d, bonito(alvo))}

    total = {
        k: sum(x[k] for x in dados)
        for k in ("efetivo", "aptos", "restritos", "fim", "administrativo", "licenca")
    }
    resumo = bloco(total, "11º GB")
    por_lotacao = "\n".join(
        f"{bonito(x['lotacao'])}: {x['efetivo']} · {x['aptos']} aptos · "
        f"{x['fim']} na atividade-fim"
        for x in dados
    )
    return {
        "total": total,
        "por_lotacao": dados,
        "mensagem": resumo + "\n\n" + por_lotacao,
    }


@router.get("/dossie")
def consultar_dossie(
    _=Depends(verificar_token),
    re: int = Query(..., description="RE do militar"),
    db: Session = Depends(get_db),
):
    """
    Dossiê consolidado do militar: dados básicos + IAS + TAF + restrições vigentes.
    1 pergunta, resposta com panorama completo. Cruza b1.efetivo, b1.ias_inspecao,
    b1.vw_taf_ultimo_apto_por_re (via buscar_taf) e b1.restricoes.
    """
    militar = db.execute(text("""
        SELECT re, nome, posto_grad, quadro, opm_efetiva, opm_atual, situacao, ativo,
               data_admissao
        FROM b1.efetivo WHERE re = :re
    """), {"re": re}).mappings().first()

    if not militar:
        raise HTTPException(status_code=404, detail=f"Militar RE={re} não encontrado")

    ias = db.execute(text("""
        SELECT numero_processo, data_validade, inspecao_medica, situacao_inspecao
        FROM b1.ias_inspecao
        WHERE re = :re ORDER BY data_validade DESC NULLS LAST LIMIT 1
    """), {"re": re}).mappings().first()

    taf, taf_posterior = buscar_taf(db, re)

    restricoes = db.execute(text("""
        SELECT origem, restricao_medica, data_inicial, data_final, observacao
        FROM b1.restricoes
        WHERE re = :re
          AND (data_final IS NULL OR data_final >= CURRENT_DATE)
          AND observacao != 'Apto Pleno'
        ORDER BY data_inicial DESC
    """), {"re": re}).mappings().all()

    # Deriva a situação da IAS
    from datetime import date
    if not ias:
        ias_situacao = "SEM IAS"
    elif ias["data_validade"] is None:
        ias_situacao = "INDETERMINADO"
    elif ias["data_validade"] < date.today():
        ias_situacao = "ATRASADA"
    elif (ias["data_validade"] - date.today()).days <= 30:
        ias_situacao = "EXPIRANDO"
    else:
        ias_situacao = "EM DIA"

    # Monta mensagem consolidada — este texto vai LITERALMENTE pro WhatsApp
    # do Comandante. Nada aqui pode ser instrução destinada ao modelo: a
    # orientação de não apresentar militar transferido como ativo fica no
    # campo 'status_atual' do JSON, que é contexto, não resposta.
    linhas = [
        f"{EMOJI['militar']} {nome_militar(militar)} (RE {militar['re']})",
    ]
    if not militar["ativo"]:
        linhas.append(
            f"⚠️ *INATIVO / TRANSFERIDO* — não faz mais parte do 11º GB."
            f"\n   Última lotação: {militar['opm_atual']}"
        )
    linhas.append(
        f"🏛 OPM efetiva: {militar['opm_efetiva']} | atual: {militar['opm_atual']}"
    )

    validade = ias["data_validade"] if ias else None
    linhas.append(
        f"{EMOJI['ias']} IAS: *{ias_situacao}*"
        + (f" — validade {fmt_data(validade)}" if validade else "")
    )

    linhas.append(f"{EMOJI['taf']} TAF: {texto_taf(taf, taf_posterior)}")

    if restricoes:
        origens = ", ".join(sorted({r["origem"] for r in restricoes if r["origem"]}))
        linhas.append(
            f"{EMOJI['restricao']} Restrições vigentes: *{len(restricoes)}*"
            + (f" ({origens})" if origens else "")
        )
    else:
        linhas.append(f"{EMOJI['restricao']} *Sem restrições vigentes*")

    return {
        "militar": dict(militar),
        "ias": {"situacao": ias_situacao, **(dict(ias) if ias else {})},
        "taf": dict(taf) if taf else None,
        "taf_ultimo_nao_apto": dict(taf_posterior) if taf_posterior else None,
        "restricoes": [dict(r) for r in restricoes],
        "mensagem": "\n".join(linhas),
    }


@router.get("/listar-com-restricao")
def listar_militares_com_restricao(
    _=Depends(verificar_token),
    lotacao: Optional[str] = Query(None, description="Filtro por lotação (1º SGB, 2º SGB, EM, etc). Opcional."),
    db: Session = Depends(get_db),
):
    """
    Lista TODOS os militares com restrição vigente hoje, com nome, posto, SGB e origem/motivo.
    Usar quando o Comandante quiser SABER QUEM ESTÁ com restrição (não só o número).
    Cenário-chave: montar escala de serviço, saber quem tirar da rotina.
    """
    filtros = ["e.ativo = true",
               "r.observacao != 'Apto Pleno'",
               "(r.data_final IS NULL OR r.data_final >= CURRENT_DATE)"]
    params = {}
    if lotacao:
        filtros.append("e.lotacao ILIKE :lotacao")
        params["lotacao"] = f"%{lotacao}%"

    where = " AND ".join(filtros)
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (e.re)
            e.re, e.posto_grad, e.nome, e.lotacao,
            r.origem, r.data_inicial, r.data_final, r.observacao, r.restricao_medica
        FROM b1.restricoes r
        JOIN b1.vw_efetivo_classificado e ON e.re = r.re
        WHERE {where}
        ORDER BY e.re, r.data_inicial DESC
    """), params).mappings().all()

    lista = [dict(r) for r in rows]

    # Agrupa por SGB pra facilitar leitura
    por_sgb = {}
    for m in lista:
        lot = m["lotacao"]
        por_sgb.setdefault(lot, []).append(m)

    partes_msg = []
    for lot in sorted(por_sgb.keys()):
        nomes = [f"{m['posto_grad']} {m['nome']} (RE {m['re']}, {m['origem']})" for m in por_sgb[lot]]
        partes_msg.append(f"*{lot}* ({len(nomes)}): " + "; ".join(nomes))

    return {
        "total": len(lista),
        "lista": lista,
        "por_sgb": {lot: por_sgb[lot] for lot in sorted(por_sgb.keys())},
        "mensagem": f"Militares com restrição vigente ({len(lista)}):\n" + "\n".join(partes_msg),
    }


@router.get("/listar-com-ias-atrasada")
def listar_militares_com_ias_atrasada(
    _=Depends(verificar_token),
    lotacao: Optional[str] = Query(None, description="Filtro por lotação. Opcional."),
    db: Session = Depends(get_db),
):
    """
    Lista TODOS os militares com IAS ATRASADA ou SEM IAS. Retorna nome, posto, SGB e validade.
    Usar quando o Comandante quiser saber QUEM está com IAS vencida (não só o número).
    """
    filtros = ["e.ativo = true"]
    params = {}
    if lotacao:
        filtros.append("e.lotacao ILIKE :lotacao")
        params["lotacao"] = f"%{lotacao}%"

    where = " AND ".join(filtros)
    rows = db.execute(text(f"""
        SELECT
            e.re, e.posto_grad, e.nome, e.lotacao,
            i.data_validade, i.numero_processo,
            CASE
                WHEN i.data_validade IS NULL         THEN 'SEM IAS'
                WHEN i.data_validade < CURRENT_DATE  THEN 'ATRASADA'
                ELSE 'OUTRA'
            END AS situacao
        FROM b1.vw_efetivo_classificado e
        LEFT JOIN LATERAL (
            SELECT data_validade, numero_processo FROM b1.ias_inspecao
            WHERE re = e.re ORDER BY data_validade DESC NULLS LAST LIMIT 1
        ) i ON true
        WHERE {where}
          AND (i.data_validade IS NULL OR i.data_validade < CURRENT_DATE)
        ORDER BY e.lotacao, i.data_validade NULLS FIRST, e.nome
    """), params).mappings().all()

    lista = [dict(r) for r in rows]
    por_sgb = {}
    for m in lista:
        por_sgb.setdefault(m["lotacao"], []).append(m)

    partes_msg = []
    for lot in sorted(por_sgb.keys()):
        detalhes = [
            f"{m['posto_grad']} {m['nome']} (RE {m['re']}, {m['situacao']}"
            + (f", validade {m['data_validade']}" if m['data_validade'] else "")
            + ")"
            for m in por_sgb[lot]
        ]
        partes_msg.append(f"*{lot}* ({len(detalhes)}): " + "; ".join(detalhes))

    return {
        "total": len(lista),
        "lista": lista,
        "por_sgb": {lot: por_sgb[lot] for lot in sorted(por_sgb.keys())},
        "mensagem": f"Militares com IAS atrasada/sem IAS ({len(lista)}):\n" + "\n".join(partes_msg),
    }


# ==========================================================================
# UGE — Controle de Processos
# ==========================================================================

@router.get("/uge-resumo")
def consultar_uge_resumo(
    _=Depends(verificar_token),
    ano: Optional[int] = Query(None, description="Ano do processo (opcional)"),
    db: Session = Depends(get_db),
):
    """Resumo dos processos administrativos da UGE: totais por status, valor empenhado, vencidos."""
    filtro = "WHERE ano = :ano" if ano else ""
    params = {"ano": ano} if ano else {}

    geral = db.execute(text(f"""
        SELECT
            COUNT(*)                                          AS total,
            COUNT(*) FILTER (WHERE status = 'ANDAMENTO')      AS em_andamento,
            COUNT(*) FILTER (WHERE status = 'ENCERRADO')      AS encerrado,
            COUNT(*) FILTER (WHERE status = 'CANCELADO')      AS cancelado,
            COALESCE(SUM(valor_empenhado), 0)                 AS total_empenhado,
            COALESCE(SUM(valor_liquidado), 0)                 AS total_liquidado,
            COUNT(*) FILTER (
                WHERE status = 'ANDAMENTO'
                  AND entrega_empenhada IS NOT NULL
                  AND entrega_empenhada < CURRENT_DATE
                  AND (entrega_prorrogada IS NULL OR entrega_prorrogada < CURRENT_DATE)
            ) AS vencidos
        FROM uge.processos {filtro}
    """), params).mappings().first()

    g = dict(geral)
    mensagem = (
        f"UGE{f' {ano}' if ano else ''}: {g['total']} processos "
        f"({g['em_andamento']} em andamento, {g['encerrado']} encerrados, {g['cancelado']} cancelados). "
        f"Empenhado: R$ {float(g['total_empenhado']):,.2f}. "
        f"Vencidos sem entrega: {g['vencidos']}."
    )
    return {"geral": g, "mensagem": mensagem}


@router.get("/uge-vencidos")
def consultar_uge_vencidos(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """Lista processos UGE em andamento com entrega vencida (empenhada e prorrogada expiradas)."""
    rows = db.execute(text("""
        SELECT numero, licitacao, objeto, solicitante, responsavel,
               valor_empenhado, entrega_empenhada, entrega_prorrogada
        FROM uge.processos
        WHERE status = 'ANDAMENTO'
          AND entrega_empenhada IS NOT NULL
          AND entrega_empenhada < CURRENT_DATE
          AND (entrega_prorrogada IS NULL OR entrega_prorrogada < CURRENT_DATE)
        ORDER BY entrega_empenhada
    """)).mappings().all()

    lista = [dict(r) for r in rows]
    if not lista:
        return {"total": 0, "lista": [], "mensagem": "Nenhum processo UGE vencido no momento."}

    partes = [
        f"Proc {p['numero']} — {p['objeto'][:60] if p['objeto'] else 'sem objeto'} "
        f"(resp: {p['responsavel'] or '—'}, venceu {p['entrega_empenhada']})"
        for p in lista
    ]
    return {
        "total": len(lista),
        "lista": lista,
        "mensagem": f"{len(lista)} processos vencidos:\n" + "\n".join(partes),
    }


# ==========================================================================
# B5 — Elogios e Láureas
# ==========================================================================

@router.get("/elogios-resumo")
def consultar_elogios_resumo(
    _=Depends(verificar_token),
    ano: Optional[int] = Query(None, description="Ano dos elogios (opcional)"),
    db: Session = Depends(get_db),
):
    """Resumo dos elogios/láureas: totais por tipo (ELO/LMP/LOU) e por SGB."""
    filtro = "AND ano = :ano" if ano else ""
    params = {"ano": ano} if ano else {}

    geral = db.execute(text(f"""
        SELECT
            COUNT(*)                                  AS total,
            COUNT(*) FILTER (WHERE tipo = 'ELO')      AS elogios,
            COUNT(*) FILTER (WHERE tipo = 'LMP')      AS lmp,
            COUNT(*) FILTER (WHERE tipo = 'LOU')      AS louvor
        FROM b5.elogios WHERE 1=1 {filtro}
    """), params).mappings().first()

    por_sgb = db.execute(text(f"""
        SELECT sgb, COUNT(*) AS total,
               COUNT(*) FILTER (WHERE tipo='ELO') AS elogios,
               COUNT(*) FILTER (WHERE tipo='LMP') AS lmp,
               COUNT(*) FILTER (WHERE tipo='LOU') AS louvor
        FROM b5.elogios WHERE sgb IS NOT NULL {filtro}
        GROUP BY sgb ORDER BY total DESC
    """), params).mappings().all()

    g = dict(geral)
    partes_sgb = [f"{r['sgb']}: {r['total']}" for r in por_sgb]
    mensagem = (
        f"Elogios/Láureas{f' {ano}' if ano else ''}: {g['total']} total "
        f"({g['elogios']} elogios, {g['lmp']} LMP, {g['louvor']} louvor). "
        f"Por SGB: {' • '.join(partes_sgb)}"
    )
    return {"geral": g, "por_sgb": [dict(r) for r in por_sgb], "mensagem": mensagem}


@router.get("/elogios-militar")
def consultar_elogios_militar(
    _=Depends(verificar_token),
    re: int = Query(..., description="RE do militar"),
    db: Session = Depends(get_db),
):
    """Retorna os elogios/láureas de um militar específico."""
    militar = db.execute(text("SELECT re, nome, posto_grad FROM b1.efetivo WHERE re = :re"),
                        {"re": re}).mappings().first()
    if not militar:
        raise HTTPException(status_code=404, detail=f"Militar RE={re} não encontrado")

    rows = db.execute(text("""
        SELECT tipo, assunto, data_elogio, sgb, solenidade, mes_ano
        FROM b5.elogios
        WHERE re::text = :re_txt OR re::text = :re_num
        ORDER BY data_elogio DESC NULLS LAST
    """), {"re_txt": str(re), "re_num": str(re)}).mappings().all()

    lista = [dict(r) for r in rows]
    resumo = {"total": len(lista),
              "elogios": sum(1 for r in lista if r["tipo"] == "ELO"),
              "lmp": sum(1 for r in lista if r["tipo"] == "LMP"),
              "louvor": sum(1 for r in lista if r["tipo"] == "LOU")}

    if not lista:
        mensagem = f"{militar['posto_grad']} {militar['nome']} (RE {militar['re']}) SEM elogios/láureas registrados."
    else:
        mensagem = (
            f"{militar['posto_grad']} {militar['nome']} (RE {militar['re']}) tem "
            f"{resumo['total']} registro(s): {resumo['elogios']} elogios, "
            f"{resumo['lmp']} LMP, {resumo['louvor']} louvor."
        )
    return {"militar": dict(militar), "resumo": resumo, "lista": lista, "mensagem": mensagem}


# ==========================================================================
# MOTOMEC — Viaturas (frota completa, não confundir com Mapa de Força)
# ==========================================================================

@router.get("/motomec-resumo")
def consultar_motomec_resumo(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """Resumo da frota (Motomec): total, operando, baixadas, idade média, % baixadas por SGB."""
    geral = db.execute(text("""
        SELECT
            COUNT(*)                                                           AS total,
            COUNT(*) FILTER (WHERE status = 'OPERANDO')                        AS operando,
            COUNT(*) FILTER (WHERE status = 'BAIXADA')                         AS baixada,
            COUNT(*) FILTER (WHERE status IN ('BAIXADA_DESCARGA','PROC_DESCARGA')) AS descarga,
            ROUND(AVG(idade_anos) FILTER (WHERE idade_anos IS NOT NULL), 1)    AS idade_media,
            ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'BAIXADA')
                / NULLIF(COUNT(*), 0), 1)                                       AS pct_baixadas
        FROM b4.vw_viaturas_situacao
    """)).mappings().first()

    por_sgb = db.execute(text("""
        SELECT sgb,
               COUNT(*)                                                          AS total,
               COUNT(*) FILTER (WHERE status = 'OPERANDO')                       AS operando,
               COUNT(*) FILTER (WHERE status = 'BAIXADA')                        AS baixada,
               ROUND(AVG(idade_anos) FILTER (WHERE idade_anos IS NOT NULL), 1)   AS idade_media
        FROM b4.vw_viaturas_situacao
        WHERE sgb IS NOT NULL
        GROUP BY sgb ORDER BY sgb
    """)).mappings().all()

    g = dict(geral)
    mensagem = (
        f"Motomec (frota completa): {g['total']} viaturas — "
        f"{g['operando']} operando, {g['baixada']} baixadas ({g['pct_baixadas']}%), "
        f"{g['descarga']} em descarga. Idade média: {g['idade_media']} anos."
    )
    return {"geral": g, "por_sgb": [dict(r) for r in por_sgb], "mensagem": mensagem}


@router.get("/motomec-baixadas")
def consultar_motomec_baixadas(
    _=Depends(verificar_token),
    sgb: Optional[str] = Query(None, description="Filtro por SGB (1º SGB, 2º SGB, etc.). Opcional."),
    db: Session = Depends(get_db),
):
    """Lista viaturas baixadas/em descarga (frota Motomec), com prefixo, tipo, idade, estação."""
    filtros = ["status IN ('BAIXADA', 'BAIXADA_DESCARGA', 'PROC_DESCARGA')"]
    params = {}
    if sgb:
        filtros.append("sgb ILIKE :sgb")
        params["sgb"] = f"%{sgb}%"

    where = " AND ".join(filtros)
    rows = db.execute(text(f"""
        SELECT prefixo, sgb, nome_estacao, municipio, tipo, modelo,
               ano_fabricacao, idade_anos, status
        FROM b4.vw_viaturas_situacao
        WHERE {where}
        ORDER BY sgb, idade_anos DESC NULLS LAST
    """), params).mappings().all()

    lista = [dict(r) for r in rows]
    if not lista:
        return {"total": 0, "lista": [], "mensagem": "Nenhuma viatura baixada encontrada."}

    partes = [
        f"{v['prefixo']} ({v['tipo']} {v['modelo'] or ''}, {v['idade_anos']} anos, "
        f"{v['sgb'] or 'sem SGB'}, {v['status']})"
        for v in lista[:20]
    ]
    extra = f" ...+{len(lista)-20} outras" if len(lista) > 20 else ""
    return {
        "total": len(lista),
        "lista": lista,
        "mensagem": f"{len(lista)} viaturas baixadas:\n" + "\n".join(partes) + extra,
    }


@router.get("/resumo-operacional")
def consultar_resumo_operacional(
    _=Depends(verificar_token),
    db: Session = Depends(get_db),
):
    """
    Retorna o resumo operacional do último snapshot do Mapa de Força:
    total de viaturas por situação, efetivo em serviço, água disponível, mergulhadores.
    Agregado por SGB.
    """
    sid = db.execute(text(
        "SELECT id, data_servico, capturado_em FROM b3.mapa_forca_snapshot_raw "
        "ORDER BY data_servico DESC NULLS LAST, capturado_em DESC LIMIT 1"
    )).mappings().first()

    if not sid:
        raise HTTPException(status_code=404, detail="Nenhum snapshot do Mapa de Força disponível")

    # Viaturas e efetivo vêm da linha; água e mergulhadores são do quartel
    # (células mescladas na planilha) e moram em b3.mapa_forca_estacao.
    geral = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE situacao = 'OPERANDO') AS viaturas_operando,
            COUNT(*) FILTER (WHERE situacao = 'RESERVA')  AS viaturas_reserva,
            COUNT(*) FILTER (WHERE situacao = 'BAIXADA')  AS viaturas_baixadas,
            COUNT(*)                                       AS viaturas_total,
            COALESCE(SUM(efetivo_qtd), 0)                 AS efetivo_total
        FROM b3.mapa_forca_linha WHERE snapshot_id = :sid
    """), {"sid": sid["id"]}).mappings().first()

    geral_estacoes = db.execute(text("""
        SELECT
            COUNT(*)                                      AS estacoes_total,
            COALESCE(SUM(capacidade_agua_l), 0)           AS agua_total_litros,
            COALESCE(SUM(mergulhadores), 0)               AS mergulhadores_total
        FROM b3.mapa_forca_estacao WHERE snapshot_id = :sid
    """), {"sid": sid["id"]}).mappings().first()

    por_sgb_viaturas = db.execute(text("""
        SELECT
            bloco_nome,
            COUNT(*) FILTER (WHERE situacao = 'OPERANDO') AS operando,
            COUNT(*) FILTER (WHERE situacao = 'RESERVA')  AS reserva,
            COUNT(*) FILTER (WHERE situacao = 'BAIXADA')  AS baixada,
            COALESCE(SUM(efetivo_qtd), 0)                 AS efetivo
        FROM b3.mapa_forca_linha WHERE snapshot_id = :sid
        GROUP BY bloco_nome
    """), {"sid": sid["id"]}).mappings().all()

    por_sgb_estacoes = db.execute(text("""
        SELECT
            bloco_nome,
            COUNT(*)                                      AS estacoes,
            COALESCE(SUM(capacidade_agua_l), 0)           AS agua_litros,
            COALESCE(SUM(mergulhadores), 0)               AS mergulhadores
        FROM b3.mapa_forca_estacao WHERE snapshot_id = :sid
        GROUP BY bloco_nome
    """), {"sid": sid["id"]}).mappings().all()

    agregado: dict = {}
    for r in por_sgb_viaturas:
        agregado[r["bloco_nome"]] = dict(r)
    for r in por_sgb_estacoes:
        agregado.setdefault(r["bloco_nome"], {"bloco_nome": r["bloco_nome"]}).update(dict(r))
    por_sgb = [agregado[k] for k in sorted(agregado)]

    g = {**dict(geral), **dict(geral_estacoes)}

    # Metadados de frescor pra o AI Agent não confundir data do snapshot com hoje
    from datetime import date
    hoje = date.today()
    data_servico = sid["data_servico"]

    # A planilha às vezes vem sem a data na A1; nesse caso o frescor é
    # calculado pela data da captura, não dá pra subtrair de None.
    if data_servico is None:
        frescor_texto = "sem data de serviço na planilha"
        data_texto = f"capturado em {sid['capturado_em'].strftime('%d/%m/%Y')}"
    else:
        dias_atras = (hoje - data_servico).days
        if dias_atras == 0:
            frescor_texto = "atualizado hoje"
        elif dias_atras == 1:
            frescor_texto = "atualizado ontem"
        else:
            frescor_texto = f"atualizado há {dias_atras} dias"
        data_texto = f"serviço de {data_servico.strftime('%d/%m/%Y')}"

    mensagem = (
        f"Mapa de Força ({frescor_texto} — {data_texto}): "
        f"{g['viaturas_operando']} operando, {g['viaturas_reserva']} reserva, {g['viaturas_baixadas']} baixada. "
        f"Efetivo total {g['efetivo_total']}, água {g['agua_total_litros']}L "
        f"em {g['estacoes_total']} estações, {g['mergulhadores_total']} mergulhadores. "
        f"(água e mergulhadores são por estação, não por viatura)"
    )
    return {
        "snapshot": {"id": sid["id"],
                     "data_servico": data_servico.isoformat() if data_servico else None,
                     "capturado_em": sid["capturado_em"].isoformat()},
        "hoje": hoje.isoformat(),
        "dias_desde_atualizacao": (hoje - data_servico).days if data_servico else None,
        "frescor": frescor_texto,
        "geral": g,
        "por_sgb": [dict(r) for r in por_sgb],
        "mensagem": mensagem,
    }
