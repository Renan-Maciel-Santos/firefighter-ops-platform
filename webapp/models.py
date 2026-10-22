from sqlalchemy import Column, Integer, String, Boolean, Enum as SAEnum
from database import Base
import enum


class PerfilEnum(str, enum.Enum):
    # Modelo em uso desde 09/09/2026. Quem decide o que cada um vê é
    # webapp/acesso.py — aqui é só o domínio da coluna.
    admin = "admin"
    oficial = "oficial"
    praca = "praca"

    # Valores antigos. Ficam porque o enum do Postgres não perde valor sem
    # recriar o tipo, e porque linha antiga precisa continuar carregando —
    # tirá-los daqui faria o login de um usuário não migrado explodir com 500.
    # Não são oferecidos no cadastro e `abas_do_usuario` não dá nenhuma aba a
    # eles: quem ficou para trás perde acesso, não ganha.
    comando = "comando"
    administrativo = "administrativo"
    operacional = "operacional"


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = {"schema": "app"}

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    matricula = Column(String, unique=True, nullable=False, index=True)
    senha_hash = Column(String, nullable=False)
    perfil = Column(SAEnum(PerfilEnum, schema="app"), nullable=False)
    ativo = Column(Boolean, default=True)
    apelido_assinatura = Column(String, nullable=True)
    # Marcado no cadastro e no reset; limpo quando o próprio usuário troca.
    # Sem isto a senha provisória vira definitiva.
    deve_trocar_senha = Column(Boolean, nullable=False, default=False)
    # Seção do EM que o praça enxerga. NULL para admin e oficial.
    secao = Column(String, nullable=True)
