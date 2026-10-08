"""ERP de Produção com IA – aplicação FastAPI."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import models  # noqa: F401  (registra as tabelas)
from .config import get_settings
from .database import Base, engine
from .routers import apontamentos, auth, cadastros, diagnostico, empresa, gemeo, gestao, ia, ordens, processos

log = logging.getLogger("erp")
STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = 1_000_000  # 1 MB

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if not s.producao:
        Base.metadata.create_all(engine)  # conveniência em desenvolvimento; produção usa Alembic
    elif s.cors_origens == ["*"]:
        raise RuntimeError("CORS '*' não é permitido em produção.")
    yield


def criar_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="ERP de Produção com IA", version="1.0.0", lifespan=lifespan,
        description="ERP genérico orientado à produção. A IA sugere; o sistema valida.",
        docs_url=None if s.producao else "/docs", redoc_url=None, openapi_url=None if s.producao else "/openapi.json")

    if s.origens_cors:
        app.add_middleware(CORSMiddleware, allow_origins=s.origens_cors, allow_credentials=False,
                           allow_methods=["GET", "POST", "PATCH", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def seguranca(request: Request, call_next):
        tamanho = request.headers.get("content-length")
        if tamanho and tamanho.isdigit() and int(tamanho) > MAX_BODY:
            return JSONResponse({"detail": "Corpo da requisição grande demais."}, status_code=413)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api"):
            resp.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith(("/docs", "/openapi")):
            resp.headers.setdefault("Content-Security-Policy", CSP)
        if s.producao:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    @app.exception_handler(IntegrityError)
    async def integridade(request: Request, exc: IntegrityError):
        log.warning("Violação de integridade: %s", exc.orig)
        return JSONResponse({"detail": "Operação conflita com dados existentes."}, status_code=409)

    @app.exception_handler(Exception)
    async def erro_generico(request: Request, exc: Exception):
        log.exception("Erro não tratado em %s", request.url.path)
        return JSONResponse({"detail": "Erro interno do servidor."}, status_code=500)

    for r in (auth, empresa, cadastros, diagnostico, processos, gemeo, ordens, apontamentos, ia, gestao):
        app.include_router(r.router, prefix="/api/v1")

    @app.get("/api/v1/saude", tags=["infra"])
    def saude():
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "ok"}

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(STATIC / "index.html")

    return app


app = criar_app()
