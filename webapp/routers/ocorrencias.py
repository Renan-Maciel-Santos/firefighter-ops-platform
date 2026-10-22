"""
Ocorrências do 11º GB (fonte: export do COBOM em b3.ocorrencias).

Substitui a versão anterior, que devolvia zeros escritos no código — a tela
parecia funcionar e informava zero incêndio.

Sobre os indicadores de tempo, porque a nomenclatura aqui importa:

  atendimento (chamada -> geração da ocorrência)
      Mediana de 3,0 min, p90 de 5,5 min. É o tempo que o COBOM leva para
      atender a ligação e abrir a ficha.

      A coluna no banco se chama `despacho_min`, mas NÃO mede despacho. O
      cruzamento com o SDOV2 fechou em 109.991 de 109.991 ocorrências: o valor
      é idêntico à fase 01 (ligação -> geração), com erro médio de 0,002 min.
      O despacho de verdade — geração até o recurso ser empenhado — é 2,6x
      maior (9,8 min em 2025) e só existe em b3.tempo_resposta. O nome da
      coluna ficou por ora porque renomeá-la mexe na view vw_ocorrencias_mensal
      e no dashboard; o rótulo exibido já foi corrigido.

  tempo-resposta (chamada -> chegada no local)
      Só em b3.tempo_resposta, fonte SDOV2, cobertura 2021 a 12/12/2025.
      Três fases: atendimento, despacho e deslocamento. O deslocamento é 76%
      do total, então é ele que manda no indicador.

  fechamento da ficha (geração -> DATAFINALIZACAO)
      Mediana de 8,7h. NÃO é duração da ocorrência: 29% de todas as
      finalizações caem entre 06:00 e 07:00, na troca de turno. O que se mede
      aqui é a disciplina de preenchimento, não o tempo de atendimento.

  duração da ocorrência (chegada -> encerramento no local)
      NÃO É CALCULÁVEL. O export do COBOM não traz carimbo de chegada nem de
      encerramento no local. Chamar o fechamento de ficha de "tempo de
      ocorrência" produziria número 100x maior que a realidade.

Estatística de tempo usa mediana e p90, nunca média: a fonte tem valores
negativos e até 143 milhões de minutos, e a média sai em 16.364 min contra
mediana de 3. Só entram no cálculo os despachos entre 0 e 120 min.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from acesso import pode_ver
from routers.auth import get_current_user

router = APIRouter(prefix="/ocorrencias", tags=["ocorrencias"])

ABA = "ocorrencias"

# Acima: Janela de sanidade do despacho. Fora dela é erro de registro, não
# desempenho — ver o cabeçalho do módulo.
JANELA_MIN = "despacho_min BETWEEN 0 AND 120"


def checar_acesso(usuario: Usuario):
    """Permissão vem de webapp/acesso.py — fonte única, ver o docstring de lá."""
    if not pode_ver(usuario, ABA):
        raise HTTPException(status_code=403, detail="Acesso negado")


def filtro_periodo(ano: Optional[int], mes: Optional[int], params: dict) -> str:
    """Monta o WHERE de período. Valores sempre por bind, nunca interpolados."""
    partes = []
    if ano:
        partes.append("extract(year FROM ocrdat) = :ano")
        params["ano"] = ano
    if mes:
        partes.append("extract(month FROM ocrdat) = :mes")
        params["mes"] = mes
    return (" WHERE " + " AND ".join(partes)) if partes else ""


@router.get("/anos")
def anos_disponiveis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    checar_acesso(current_user)
    rows = db.execute(text("""
        SELECT extract(year FROM ocrdat)::int AS ano, count(*) AS total
          FROM b3.ocorrencias
         GROUP BY 1 ORDER BY 1 DESC
    """)).mappings().all()
    # Acima: Até onde vai cada fonte, para a nota da tela não envelhecer com
    # datas escritas no HTML (o COBOM é recarregado; o SDOV2 parou em 2025).
    cob = db.execute(text("""
        SELECT (SELECT max(ocrdat) FROM b3.ocorrencias)              AS cobom_ate,
               (SELECT min(dt_ocorrencia)::date FROM b3.tempo_resposta) AS sdov_de,
               (SELECT max(dt_ocorrencia)::date FROM b3.tempo_resposta) AS sdov_ate
    """)).mappings().first()
    return {"data": [dict(r) for r in rows], "cobertura": dict(cob) if cob else {}}


@router.get("/resumo")
def resumo(
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    checar_acesso(current_user)
    params: dict = {}
    onde = filtro_periodo(ano, mes, params)

    row = db.execute(text(f"""
        SELECT count(*)                                              AS total,
               count(DISTINCT natcod)                                AS naturezas,
               min(ocrdat)                                           AS primeira,
               max(ocrdat)                                           AS ultima,
               count(*) FILTER (WHERE {JANELA_MIN})                  AS com_tempo,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY despacho_min)
                     FILTER (WHERE {JANELA_MIN})::numeric, 1)        AS despacho_mediana,
               round(percentile_cont(0.9) WITHIN GROUP (ORDER BY despacho_min)
                     FILTER (WHERE {JANELA_MIN})::numeric, 1)        AS despacho_p90,
               round(percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY extract(epoch FROM (dt_finalizacao - dt_geracao))/3600)
                     FILTER (WHERE dt_finalizacao IS NOT NULL
                             AND dt_geracao IS NOT NULL
                             AND dt_finalizacao > dt_geracao)::numeric, 1)
                                                                     AS ficha_mediana_h
          FROM b3.ocorrencias{onde}
    """), params).mappings().first()

    return dict(row) if row else {}


@router.get("/tempo-resposta")
def tempo_resposta(
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Tempo-resposta em três fases, do SDOV2 (b3.tempo_resposta).

    Fonte diferente da desta tela: o export do COBOM não traz carimbo de
    chegada no local, então o tempo do despacho até o bombeiro chegar só existe
    aqui. Cobertura de 2021 a 12/12/2025 — em ano sem carga o endpoint devolve
    ocorrencias=0, e a tela precisa dizer "sem dado" em vez de mostrar traço,
    que se confunde com falha.
    """
    checar_acesso(current_user)
    params: dict = {}
    partes = []
    if ano:
        partes.append("extract(year FROM dt_ocorrencia) = :ano")
        params["ano"] = ano
    if mes:
        partes.append("extract(month FROM dt_ocorrencia) = :mes")
        params["mes"] = mes
    onde = (" WHERE " + " AND ".join(partes)) if partes else ""

    row = db.execute(text(f"""
        SELECT count(*)                                                    AS ocorrencias,
               round(percentile_cont(0.5) WITHIN GROUP
                     (ORDER BY t_total_min)::numeric, 1)                   AS total_mediana,
               round(percentile_cont(0.9) WITHIN GROUP
                     (ORDER BY t_total_min)::numeric, 1)                   AS total_p90,
               round(percentile_cont(0.5) WITHIN GROUP
                     (ORDER BY t_atendimento_min)::numeric, 1)             AS atendimento_mediana,
               round(percentile_cont(0.5) WITHIN GROUP
                     (ORDER BY t_despacho_min)::numeric, 1)                AS despacho_mediana,
               round(percentile_cont(0.5) WITHIN GROUP
                     (ORDER BY t_deslocamento_min)::numeric, 1)            AS deslocamento_mediana,
               round(100.0 * sum(t_deslocamento_min)
                     / nullif(sum(t_total_min), 0), 1)                     AS pct_deslocamento
          FROM b3.vw_tempo_resposta_ocorrencia{onde}
    """), params).mappings().first()

    # Acima: O intervalo coberto vai junto para a tela poder explicar um zero.
    limites = db.execute(text("""
        SELECT min(dt_ocorrencia)::date AS de, max(dt_ocorrencia)::date AS ate
          FROM b3.tempo_resposta
    """)).mappings().first()

    dados = dict(row) if row else {}
    dados["cobertura_de"] = limites["de"] if limites else None
    dados["cobertura_ate"] = limites["ate"] if limites else None
    return dados


@router.get("/tempo-resposta-anual")
def tempo_resposta_anual(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Série anual das três fases — o gráfico que mostra onde o tempo se perde."""
    checar_acesso(current_user)
    rows = db.execute(text("""
        SELECT ano, ocorrencias, atendimento_medio, despacho_medio,
               deslocamento_medio, total_medio, total_mediana
          FROM b3.vw_tempo_resposta_anual
         ORDER BY ano
    """)).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.get("/tempo-resposta-municipio")
def tempo_resposta_municipio(
    limite: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Piores deslocamentos por município — leitura de vazio de cobertura."""
    checar_acesso(current_user)
    rows = db.execute(text("""
        SELECT municipio, ocorrencias, deslocamento_mediana, total_medio
          FROM b3.vw_tempo_resposta_municipio
         LIMIT :limite
    """), {"limite": limite}).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.get("/serie-mensal")
def serie_mensal(
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Série por mês: volume e tempo de despacho. Base do gráfico principal."""
    checar_acesso(current_user)
    params: dict = {}
    onde = filtro_periodo(ano, None, params)

    rows = db.execute(text(f"""
        SELECT to_char(date_trunc('month', ocrdat), 'MM/YYYY')       AS rotulo,
               date_trunc('month', ocrdat)::date                     AS mes,
               count(*)                                              AS ocorrencias,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY despacho_min)
                     FILTER (WHERE {JANELA_MIN})::numeric, 1)        AS mediana,
               round(percentile_cont(0.9) WITHIN GROUP (ORDER BY despacho_min)
                     FILTER (WHERE {JANELA_MIN})::numeric, 1)        AS p90
          FROM b3.ocorrencias{onde}
         GROUP BY 1, 2 ORDER BY 2
    """), params).mappings().all()

    return {"data": [dict(r) for r in rows]}


@router.get("/por-sgb")
def por_sgb(
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    checar_acesso(current_user)
    params: dict = {}
    onde = filtro_periodo(ano, mes, params)

    rows = db.execute(text(f"""
        SELECT coalesce(sgb, 'não informado')                        AS sgb,
               count(*)                                              AS ocorrencias,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY despacho_min)
                     FILTER (WHERE {JANELA_MIN})::numeric, 1)        AS mediana
          FROM b3.ocorrencias{onde}
         GROUP BY 1 ORDER BY 2 DESC
    """), params).mappings().all()

    return {"data": [dict(r) for r in rows]}


@router.get("/por-natureza")
def por_natureza(
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    limite: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Top naturezas.

    Devolve o CÓDIGO do COBOM (ex: N01, L08), não a descrição: não existe
    tabela de domínio das 93 naturezas. Enquanto ela não chegar, agrupar em
    "Incêndio / Salvamento / APH" seria invenção.
    """
    checar_acesso(current_user)
    params: dict = {"limite": limite}
    onde = filtro_periodo(ano, mes, params)

    rows = db.execute(text(f"""
        SELECT coalesce(natcod, 'sem código')                        AS natcod,
               count(*)                                              AS ocorrencias
          FROM b3.ocorrencias{onde}
         GROUP BY 1 ORDER BY 2 DESC LIMIT :limite
    """), params).mappings().all()

    return {"data": [dict(r) for r in rows]}


@router.get("/hora-fechamento")
def hora_fechamento(
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Distribuição da hora em que a ficha é fechada.

    Existe para deixar visível por que o intervalo até a finalização não pode
    ser lido como duração da ocorrência: o pico às 06h e 07h é a troca de turno.
    """
    checar_acesso(current_user)
    params: dict = {}
    onde = filtro_periodo(ano, None, params)
    juncao = " AND " if onde else " WHERE "

    rows = db.execute(text(f"""
        SELECT extract(hour FROM dt_finalizacao)::int                AS hora,
               count(*)                                              AS fechamentos
          FROM b3.ocorrencias{onde}{juncao}dt_finalizacao IS NOT NULL
         GROUP BY 1 ORDER BY 1
    """), params).mappings().all()

    return {"data": [dict(r) for r in rows]}


@router.get("/")
def listar(
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    sgb: Optional[str] = None,
    natcod: Optional[str] = None,
    busca: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    checar_acesso(current_user)

    params: dict = {}
    filtros = []
    if ano:
        filtros.append("extract(year FROM ocrdat) = :ano")
        params["ano"] = ano
    if mes:
        filtros.append("extract(month FROM ocrdat) = :mes")
        params["mes"] = mes
    if sgb:
        filtros.append("sgb = :sgb")
        params["sgb"] = sgb
    if natcod:
        filtros.append("natcod = :natcod")
        params["natcod"] = natcod
    if busca:
        filtros.append("(logradouro_inicial ILIKE :busca OR bairro_inicial ILIKE :busca"
                       " OR dados_complementares ILIKE :busca)")
        params["busca"] = f"%{busca}%"

    base = " FROM b3.ocorrencias"
    if filtros:
        base += " WHERE " + " AND ".join(filtros)

    total = db.execute(text(f"SELECT count(*){base}"), params).scalar()

    params["limit"] = limit
    params["offset"] = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT id, ocrnum, ocrdat, natcod, sgb,
               dt_chamada, dt_geracao, dt_finalizacao, despacho_min,
               logradouro_inicial, numero_inicial, bairro_inicial,
               left(coalesce(dados_complementares, ''), 160) AS resumo
          {base}
         ORDER BY ocrdat DESC, dt_chamada DESC NULLS LAST
         LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "data": [dict(r) for r in rows],
    }
