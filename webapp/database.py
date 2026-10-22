import os
import sys
os.environ["PGPASSFILE"] = ""  # desabilita leitura do pgpass.conf do Windows

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Acima: Permite importar _env da raiz do projeto (o webapp roda com cwd em webapp/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import exigir, opcional

# Acima: Credenciais do .env da raiz. Antes a URL vinha escrita aqui, com usuário e
# senha em texto claro — o primeiro lugar onde alguém com acesso ao fonte olharia.
from urllib.parse import quote_plus

_USER = opcional("PG_USER", "admin")
_PASS = quote_plus(exigir("PG_PASS"))
_HOST = opcional("PG_HOST", "localhost")
_PORT = opcional("PG_PORT", "5432")
_DB = opcional("PG_DB", "11gb")

DATABASE_URL = f"postgresql+psycopg2://{_USER}:{_PASS}@{_HOST}:{_PORT}/{_DB}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
