"""
Gestão de usuários pelo painel — só para o perfil `admin`.

Espelha o que webapp/gerenciar_usuarios.py faz pelo terminal. Os dois
continuam existindo de propósito: é pelo script que se recupera o acesso se o
último admin se perder, e o script não depende do webapp estar de pé.

SENHAS
Nenhum endpoint aqui devolve, aceita ou compara hash. A senha provisória é
gerada, aplicada e devolvida UMA vez na resposta do cadastro ou do reset — não
fica em lugar nenhum depois disso. Trocar a senha é ação do próprio dono, em
/auth/trocar-senha; ninguém troca a senha de outro, só reseta para uma
provisória que o dono é obrigado a substituir.
"""

import secrets
import sys
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from routers.auth import get_current_user, hash_password
from acesso import PERFIS, SECOES, abas_do_usuario, pode_ver
from eap_documento import POSTOS, nome_proprio
from sqlalchemy import text

router = APIRouter(prefix="/usuarios", tags=["usuarios"])



def exigir_admin(user: Usuario) -> Usuario:
    """Só o admin gerencia acesso. Regra em webapp/acesso.py."""
    if not pode_ver(user, "usuarios"):
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador")
    return user


def senha_provisoria() -> str:
    # ~12 caracteres: forte o bastante e ainda digitável uma vez. Existe para
    # ser trocada no primeiro acesso, não para durar.
    return secrets.token_urlsafe(9)


class NovoUsuario(BaseModel):
    matricula: str
    nome: str
    perfil: str
    secao: str | None = None
    apelido_assinatura: str | None = None


class MudarAtivo(BaseModel):
    ativo: bool


def _saida(u: Usuario) -> dict:
    return {
        "id": u.id,
        "nome": u.nome,
        "matricula": u.matricula,
        "perfil": u.perfil.value,
        "secao": u.secao,
        # As abas vão junto para o painel mostrar o que a pessoa enxerga sem
        # reimplementar a regra. Quem decide continua sendo o acesso.py.
        "abas": list(abas_do_usuario(u.perfil.value, u.secao)),
        "ativo": bool(u.ativo),
        "deve_trocar_senha": bool(u.deve_trocar_senha),
        "apelido_assinatura": u.apelido_assinatura,
    }


@router.get("")
def listar(db: Session = Depends(get_db),
           atual: Usuario = Depends(get_current_user)):
    exigir_admin(atual)
    return {
        "eu": atual.id,
        "perfis": list(PERFIS),
        "secoes": list(SECOES),
        "usuarios": [_saida(u) for u in db.query(Usuario).order_by(Usuario.nome).all()],
    }


# OPM do efetivo -> seção do painel que o praça dali enxerga. Só o EM tem
# seção; praça de SGB não recebe login (ver acesso.py). NATs dos SGBs
# (99011x900) são da SAT.
SECAO_POR_OPM = {
    990119110: "B/1 e B/5",
    990119130: "B/3, PJMD e Motomec",
    990119131: "COBOM",
    990119140: "B/4",
    990119160: "St UGE",
    990119100: "SAT",
    990119200: "SAT",
    990111900: "SAT", 990112900: "SAT", 990113900: "SAT", 990114900: "SAT",
}


@router.get("/efetivo/{re}")
def buscar_no_efetivo(re: int, db: Session = Depends(get_db),
                      atual: Usuario = Depends(get_current_user)):
    """Preenche o cadastro a partir do RE: nome, e perfil/seção sugeridos."""
    exigir_admin(atual)
    m = db.execute(text("""
        SELECT e.nome, e.posto_grad, e.cod_opm_atual, e.opm_atual, v.posto_qpo, v.lotacao
          FROM b1.efetivo e
          JOIN b1.vw_efetivo_classificado v ON v.re = e.re
         WHERE e.re = :re AND e.ativo
    """), {"re": re}).mappings().first()
    if not m:
        raise HTTPException(status_code=404, detail=f"RE {re} não está no efetivo ativo.")
    oficial = m["posto_qpo"] in ("Ten Cel PM", "Maj PM", "Cap PM", "Ten PM")
    secao = None if oficial else SECAO_POR_OPM.get(m["cod_opm_atual"])
    return {
        "nome": nome_proprio(m["nome"]),
        "posto": POSTOS.get(m["posto_grad"], m["posto_grad"]),
        "opm": m["opm_atual"],
        "lotacao": m["lotacao"],
        "perfil": "oficial" if oficial else "praca",
        "secao": secao,
        "ja_cadastrado": db.query(Usuario).filter(Usuario.matricula == str(re)).first() is not None,
    }


@router.post("")
def criar(dados: NovoUsuario, db: Session = Depends(get_db),
          atual: Usuario = Depends(get_current_user)):
    exigir_admin(atual)

    if dados.perfil not in PERFIS:
        raise HTTPException(status_code=400, detail=f"Perfil inválido: {dados.perfil}")

    # Praça sem seção não veria aba nenhuma. Barrar no cadastro em vez de
    # deixar criar uma conta que entra e não mostra nada.
    secao = (dados.secao or "").strip() or None
    if dados.perfil == "praca":
        if not secao:
            raise HTTPException(status_code=400,
                                detail="Escolha a seção que este praça vai enxergar.")
        if secao not in SECOES:
            raise HTTPException(status_code=400, detail=f"Seção inválida: {secao}")
    else:
        # admin e oficial veem tudo; seção aqui só confundiria a leitura.
        secao = None

    matricula = dados.matricula.strip()
    nome = dados.nome.strip()
    if not matricula or not nome:
        raise HTTPException(status_code=400, detail="Matrícula e nome são obrigatórios")

    if db.query(Usuario).filter(Usuario.matricula == matricula).first():
        raise HTTPException(
            status_code=409,
            detail=f"Matrícula {matricula} já cadastrada. Para trocar a senha dela, use Resetar.",
        )

    senha = senha_provisoria()
    u = Usuario(
        nome=nome, matricula=matricula, senha_hash=hash_password(senha),
        perfil=dados.perfil, secao=secao, ativo=True,
        apelido_assinatura=(dados.apelido_assinatura or None),
        deve_trocar_senha=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"usuario": _saida(u), "senha_provisoria": senha}


@router.post("/{usuario_id}/resetar")
def resetar(usuario_id: int, db: Session = Depends(get_db),
            atual: Usuario = Depends(get_current_user)):
    exigir_admin(atual)
    u = db.get(Usuario, usuario_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    senha = senha_provisoria()
    u.senha_hash = hash_password(senha)
    u.deve_trocar_senha = True
    db.commit()
    return {"usuario": _saida(u), "senha_provisoria": senha}


@router.patch("/{usuario_id}/ativo")
def mudar_ativo(usuario_id: int, dados: MudarAtivo, db: Session = Depends(get_db),
                atual: Usuario = Depends(get_current_user)):
    exigir_admin(atual)
    u = db.get(Usuario, usuario_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Duas travas contra ficar trancado do lado de fora. Nenhuma delas existe
    # no script de terminal: lá quem roda já está na máquina e tem como
    # desfazer. Aqui, não.
    if not dados.ativo and u.id == atual.id:
        raise HTTPException(
            status_code=400,
            detail="Você não pode desativar a própria conta.",
        )

    if not dados.ativo and u.perfil.value == "admin":
        outros = db.query(Usuario).filter(
            Usuario.perfil == "admin", Usuario.ativo == True,  # noqa: E712
            Usuario.id != u.id,
        ).count()
        if outros == 0:
            raise HTTPException(
                status_code=400,
                detail="Este é o último administrador ativo. Desativá-lo "
                       "deixaria o sistema sem quem gerencia acessos.",
            )

    u.ativo = bool(dados.ativo)
    db.commit()
    return {"usuario": _saida(u)}
