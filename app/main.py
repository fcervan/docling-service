"""API HTTP: recebe um documento e devolve o JSON estruturado do Docling."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware

from . import __version__
from .auth import verificar_api_key
from .config import ALLOWED_MIMES, DANGEROUS_MIMES, SUPPORTED, get_settings
from .converter import ConversionError, converter, versao_docling
from .schemas import ConvertResponse, HealthResponse, InfoResponse

logger = logging.getLogger("docling-service")

_DOCS = os.getenv("DOCLING_DOCS_ENABLED", "1").strip().lower() not in {"0", "false", "no"}

app = FastAPI(
    title="Docling Service",
    version=__version__,
    description="Converta documentos para o JSON estruturado do Docling.",
    docs_url="/docs" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
    redoc_url=None,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("DOCLING_MAX_WORKERS", "2"))),
    thread_name_prefix="docling",
)


@app.middleware("http")
async def _headers_de_seguranca(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Request-ID", uuid.uuid4().hex)
    return response


def _nome_seguro(nome: str | None) -> str:
    base = (nome or "").replace("\\", "/").split("/")[-1].strip()
    base = "".join(c for c in base if c.isprintable()).strip()
    if base in {"", ".", ".."}:
        return ""
    return base[:200]


def _validar_mime(content_type: str | None) -> None:
    tipo = (content_type or "").split(";", 1)[0].strip().lower()
    if tipo in DANGEROUS_MIMES or any(
        s in tipo for s in ("executable", "x-msdownload", "x-dosexec", "x-elf", "x-shellscript")
    ):
        raise HTTPException(status_code=415, detail="Tipo de arquivo não permitido")
    if tipo and tipo not in ALLOWED_MIMES and not tipo.startswith("text/"):
        raise HTTPException(status_code=415, detail="Tipo de arquivo não permitido")


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    return {"ok": True}


@app.get("/v1/info", response_model=InfoResponse)
def info() -> dict:
    settings = get_settings()
    return {
        "service": "docling-service",
        "schema_version": settings.schema_version,
        "docling_version": versao_docling(),
        "supported_extensions": list(SUPPORTED),
        "max_upload_mb": settings.max_upload_mb,
        "convert_timeout_seconds": settings.convert_timeout,
    }


@app.post("/v1/convert", response_model=ConvertResponse)
async def convert_document(
    file: UploadFile = File(...),
    app_name: str = Depends(verificar_api_key),
) -> ConvertResponse:
    settings = get_settings()
    nome = _nome_seguro(file.filename)
    if not nome:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    if Path(nome).suffix.lower() not in SUPPORTED:
        raise HTTPException(status_code=415, detail="Extensão de arquivo não suportada")
    _validar_mime(file.content_type)

    conteudo = await file.read(settings.max_upload_bytes + 1)
    if len(conteudo) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Arquivo excede o limite configurado")
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    tmpdir = Path(tempfile.mkdtemp(prefix="docling-"))
    destino = tmpdir / nome
    destino.write_bytes(conteudo)
    loop = asyncio.get_running_loop()
    futuro = loop.run_in_executor(_EXECUTOR, converter, destino)
    limite = settings.convert_timeout
    try:
        resultado = await asyncio.wait_for(asyncio.shield(futuro), timeout=limite)
    except asyncio.TimeoutError:
        futuro.add_done_callback(lambda _f: shutil.rmtree(tmpdir, ignore_errors=True))
        logger.warning("timeout app=%s arquivo=%s limite=%.0fs", app_name, nome, limite)
        raise HTTPException(status_code=504, detail="Tempo de conversão excedido") from None
    except ConversionError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        logger.exception("falha de conversão app=%s arquivo=%s", app_name, nome)
        raise HTTPException(
            status_code=422, detail="Não foi possível converter o documento"
        ) from None
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        logger.exception("erro inesperado app=%s arquivo=%s", app_name, nome)
        raise HTTPException(status_code=500, detail="Erro interno na conversão") from None
    shutil.rmtree(tmpdir, ignore_errors=True)

    logger.info(
        "convertido app=%s arquivo=%s tamanho=%d tabelas=%d",
        app_name,
        nome,
        len(conteudo),
        resultado["tabelas"],
    )
    return ConvertResponse(
        schema_version=settings.schema_version,
        docling_version=versao_docling(),
        filename=nome,
        tabelas=resultado["tabelas"],
        markdown=resultado["markdown"],
        document=resultado["document"],
    )
