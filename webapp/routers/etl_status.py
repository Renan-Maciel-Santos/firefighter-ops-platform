from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from routers.auth import get_current_user

router = APIRouter(prefix="/etl-status", tags=["etl-status"])


# Mapeia o domínio interno (como está gravado em b1.etl_status) → rótulo amigável no painel
LABELS = {
    "efetivo": "Efetivo",
    "ias": "Inspeção Anual (IAS)",
    "restricoes": "Restrições",
    "mapa_forca": "Mapa de Força",
    "afastamentos": "Afastamentos",
    "b4_viaturas": "Viaturas",
}

# Domínios que aparecem no card resumo do painel (ordem = ordem de exibição)
DOMINIOS_PRINCIPAIS = ["efetivo", "ias", "restricoes", "mapa_forca"]


@router.get("/")
def listar_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna o status de cada ETL relevante, com tempo desde a última execução.

    Frontend usa os campos:
    - status: 'success', 'error', 'running'
    - finalizado_em: ISO datetime ou None
    - segundos_desde: quantos segundos se passaram desde o último sucesso (None se nunca completou)
    - linhas_lidas/inseridas/atualizadas: métricas da última execução
    - erro: mensagem de erro (só se status='error')
    """
    rows = db.execute(text("""
        SELECT
            dominio,
            status,
            iniciado_em,
            finalizado_em,
            EXTRACT(EPOCH FROM (now() - COALESCE(finalizado_em, iniciado_em))) AS segundos_desde,
            linhas_lidas,
            linhas_inseridas,
            linhas_atualizadas,
            erro
        FROM b1.etl_status
        WHERE dominio = ANY(:dominios)
        ORDER BY array_position(:dominios, dominio);
    """), {"dominios": DOMINIOS_PRINCIPAIS}).mappings().all()

    resultado = []
    for r in rows:
        resultado.append({
            "dominio": r["dominio"],
            "label": LABELS.get(r["dominio"], r["dominio"]),
            "status": (r["status"] or "").lower(),
            "iniciado_em": r["iniciado_em"].isoformat() if r["iniciado_em"] else None,
            "finalizado_em": r["finalizado_em"].isoformat() if r["finalizado_em"] else None,
            "segundos_desde": int(r["segundos_desde"]) if r["segundos_desde"] is not None else None,
            "linhas_lidas": r["linhas_lidas"],
            "linhas_inseridas": r["linhas_inseridas"],
            "linhas_atualizadas": r["linhas_atualizadas"],
            "erro": r["erro"],
        })

    return {"data": resultado}
