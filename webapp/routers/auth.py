from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from models import Usuario
from acesso import abas_do_usuario

# Acima: Raiz do projeto, para alcançar o _env (este arquivo está em webapp/routers/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _env import exigir, opcional

# Acima: Esta chave assina os tokens de sessão. Enquanto esteve no fonte, qualquer pessoa
# com acesso ao código podia forjar um token de qualquer perfil, inclusive administrador,
# para um sistema com dados de pessoal, saúde e disciplina. A chave anterior foi
# descartada — tokens emitidos com ela deixaram de valer, e é esse o efeito desejado.
SECRET_KEY = exigir("JWT_SECRET_KEY", "Gere uma nova com: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(opcional("JWT_EXPIRE_HOURS", "8"))

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str
    perfil: str
    nome: str
    deve_trocar_senha: bool = False


class LoginForm(BaseModel):
    matricula: str
    senha: str


class TrocaSenhaForm(BaseModel):
    senha_atual: str
    senha_nova: str


# Mínimo de 8 caracteres. Não é política de segurança sofisticada — é o piso
# para que a senha provisória gerada no cadastro não seja trocada por "1234".
SENHA_MIN = 8


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        matricula: str = payload.get("sub")
        if matricula is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = db.query(Usuario).filter(Usuario.matricula == matricula, Usuario.ativo == True).first()
    if user is None:
        raise credentials_exception
    return user


@router.post("/login", response_model=Token)
def login(form: LoginForm, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(
        Usuario.matricula == form.matricula,
        Usuario.ativo == True
    ).first()
    if not user or not verify_password(form.senha, user.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Matrícula ou senha incorretos"
        )
    token = create_access_token({"sub": user.matricula, "perfil": user.perfil.value})
    return Token(
        access_token=token, token_type="bearer",
        perfil=user.perfil.value, nome=user.nome,
        deve_trocar_senha=bool(user.deve_trocar_senha),
    )


@router.get("/me")
def get_me(current_user: Usuario = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "nome": current_user.nome,
        "matricula": current_user.matricula,
        "perfil": current_user.perfil.value,
        "secao": current_user.secao,
        # O painel monta o menu com ISTO, e não com uma lista própria em
        # JavaScript. Duas fontes para a mesma decisão divergem em silêncio.
        "abas": list(abas_do_usuario(current_user.perfil.value, current_user.secao)),
        "deve_trocar_senha": bool(current_user.deve_trocar_senha),
    }


@router.post("/trocar-senha")
def trocar_senha(
    form: TrocaSenhaForm,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """O próprio usuário troca a senha. Ninguém troca a senha de outro.

    Quem cadastra vê a provisória uma vez, no terminal, e nunca mais — o banco
    guarda só o hash bcrypt. Se o usuário esquecer, o caminho é resetar (gera
    outra provisória), não recuperar: a senha antiga não é recuperável nem
    para o administrador, e é esse o comportamento desejado.
    """
    if not verify_password(form.senha_atual, current_user.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")

    if len(form.senha_nova) < SENHA_MIN:
        raise HTTPException(
            status_code=400,
            detail=f"A senha nova precisa de pelo menos {SENHA_MIN} caracteres",
        )

    if form.senha_nova == form.senha_atual:
        raise HTTPException(
            status_code=400, detail="A senha nova tem de ser diferente da atual"
        )

    current_user.senha_hash = hash_password(form.senha_nova)
    current_user.deve_trocar_senha = False
    db.commit()
    return {"ok": True, "mensagem": "Senha alterada."}
