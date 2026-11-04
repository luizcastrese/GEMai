"""ERP de Produção com IA – aplicação FastAPI."""
import hashlib
import logging
import re
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import models  # noqa: F401  (registra as tabelas)
from .config import get_settings
from .database import Base, engine
from .migrar import aplicar_migracoes, url_postgres
from .routers import apontamentos, auth, cadastros, calibracao, contorno, diagnostico, empresa, gemeo, gestao, ia, inicio, meios, ordens, planos, processos

log = logging.getLogger("erp")
STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = 1_000_000  # 1 MB

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@lru_cache
def versao_estaticos() -> str:
    """Muda a cada deploy (mtime/tamanho dos JS/CSS) para cache-bust em /."""
    h = hashlib.sha256()
    if STATIC.exists():
        for p in sorted(STATIC.iterdir()):
            if p.is_file() and p.suffix in {".js", ".css"}:
                st = p.stat()
                h.update(f"{p.name}:{st.st_mtime_ns}:{st.st_size}".encode())
    return h.hexdigest()[:12] or "0"


def html_com_versao(html: str, versao: str) -> str:
    return (html
            .replace('href="/static/style.css"', f'href="/static/style.css?v={versao}"')
            .replace('src="/static/app.js"', f'src="/static/app.js?v={versao}"'))


_JS_FROM = re.compile(r"""(\bfrom\s+['"])(\./[^'"]+\.js)(['"])""")


def js_com_versao(src: str, versao: str) -> str:
    """Cache-bust imports relativos (o ?v= do HTML só vale para o app.js de entrada)."""
    return _JS_FROM.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={versao}{m.group(3)}", src)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if url_postgres(s.database_url):
        log.info("Aplicando migrações Alembic (Postgres).")
        aplicar_migracoes(s.database_url)
    elif not s.producao:
        Base.metadata.create_all(engine)  # conveniência em desenvolvimento; produção usa Alembic
    if s.producao and s.cors_origens == ["*"]:
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
        limite = MAX_BODY
        if request.url.path == "/api/v1/meios/identificar":  # única rota que recebe foto (JPEG/PNG em base64)
            limite = max(MAX_BODY, s.foto_max_bytes * 4 // 3 + 20_000)
        if tamanho and tamanho.isdigit() and int(tamanho) > limite:
            return JSONResponse({"detail": "Corpo da requisição grande demais."}, status_code=413)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api"):
            resp.headers.setdefault("Cache-Control", "no-store")
        elif request.url.path == "/" or request.url.path.startswith("/static"):
            resp.headers["Cache-Control"] = "no-cache"
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

    for r in (auth, empresa, cadastros, diagnostico, processos, gemeo, ordens, apontamentos, ia, gestao, inicio, contorno, planos, meios, calibracao):
        app.include_router(r.router, prefix="/api/v1")

    @app.get("/api/v1/saude", tags=["infra"])
    def saude():
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "ok"}

    if STATIC.exists():
        raiz_static = STATIC.resolve()

        @app.get("/static/{caminho:path}", include_in_schema=False)
        def estatico(caminho: str):
            alvo = (STATIC / caminho).resolve()
            if not alvo.is_relative_to(raiz_static) or not alvo.is_file():
                raise HTTPException(404)
            if alvo.suffix == ".js":
                corpo = js_com_versao(alvo.read_text(encoding="utf-8"), versao_estaticos())
                return Response(corpo, media_type="text/javascript; charset=utf-8")
            return FileResponse(alvo)

        @app.get("/", include_in_schema=False)
        def index():
            html = (STATIC / "index.html").read_text(encoding="utf-8")
            return HTMLResponse(html_com_versao(html, versao_estaticos()))

    return app


app = criar_app()
