from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from database import engine, Base
from models import Usuario  # noqa: F401  (registra o modelo no metadata)
from routers import auth, viaturas, pessoal, ocorrencias, ppmq, saude, taf, mapa_forca, elogios, uge, etl_status, consulta, sjd, usuarios, auditoria_cobom, eap

app = FastAPI(title="11º GB — Sistema Interno", version="1.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(viaturas.router)
app.include_router(pessoal.router)
app.include_router(ocorrencias.router)
app.include_router(ppmq.router)
app.include_router(saude.router)
app.include_router(taf.router)
app.include_router(mapa_forca.router)
app.include_router(elogios.router)
app.include_router(uge.router)
app.include_router(etl_status.router)
app.include_router(consulta.router)
app.include_router(sjd.router)
app.include_router(usuarios.router)
app.include_router(auditoria_cobom.router)
app.include_router(eap.router)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))


@app.get("/corrida", include_in_schema=False)
def corrida():
    return FileResponse(os.path.join(FRONTEND_DIR, "corrida.html"))


@app.get("/health")
def health():
    return {"status": "ok", "sistema": "11º GB PMESP"}
