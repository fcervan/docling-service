"""Wrapper fino em volta do Docling (import lazy para testes e startup leve).

Os modelos do Docling ficam residentes depois da primeira conversão. Para não
segurar ~1.5 GiB em um host pequeno, o serviço:
- reaproveita um converter por modo de OCR (evita recarregar modelos por request);
- converte sem OCR por padrão e só repete com OCR se o texto extraído for
  residual (PDF escaneado);
- expõe `liberar()` para o monitor de idle descartar os modelos.
"""

from __future__ import annotations

import ctypes
import gc
import logging
import threading
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

logger = logging.getLogger("docling-service.converter")


class ConversionError(Exception):
    """Falha de conversão (mensagem segura para o cliente)."""


_converters: dict[bool, Any] = {}
_lock = threading.Lock()
_ultimo_uso: float | None = None


def versao_docling() -> str:
    try:
        return version("docling")
    except PackageNotFoundError:
        return "desconhecida"


def _carregar(ocr: bool):
    """Cria um DocumentConverter (import lazy: só na primeira conversão)."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opcoes = PdfPipelineOptions()
    opcoes.do_ocr = ocr
    opcoes.do_table_structure = True  # tabelas viram chunks próprios no RAG
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opcoes)}
    )


def _converter_para(ocr: bool):
    if ocr not in _converters:
        _converters[ocr] = _carregar(ocr)
    return _converters[ocr]


def _paginas(doc) -> int:
    try:
        return max(1, len(getattr(doc, "pages", None) or {}))
    except Exception:
        return 1


def _tem_texto_suficiente(doc, minimo_por_pagina: int) -> bool:
    """Heurística: PDF escaneado extrai quase nada sem OCR."""
    total = 0
    for item in getattr(doc, "texts", None) or []:
        total += len((getattr(item, "text", "") or "").strip())
    return total >= minimo_por_pagina * _paginas(doc)


def _exportar(doc) -> dict:
    document = doc.export_to_dict()
    markdown = doc.export_to_markdown()
    try:
        tabelas = len(doc.tables or [])
    except Exception:
        tabelas = 0
    return {"document": document, "markdown": markdown, "tabelas": tabelas}


def converter(caminho: Path) -> dict:
    """Converte um arquivo local e devolve document/markdown/tabelas."""
    global _ultimo_uso
    from .config import get_settings

    try:
        settings = get_settings()
        modo = settings.ocr_mode
        usar_ocr = modo == "on"
        # Serializa: um único conjunto de modelos em memória (Docling não é
        # thread-safe e duas cópias dobram o RSS em hosts pequenos).
        with _lock:
            _ultimo_uso = time.monotonic()
            resultado = _converter_para(usar_ocr).convert(str(caminho))
            doc = resultado.document
            if (
                modo == "auto"
                and not usar_ocr
                and caminho.suffix.lower() == ".pdf"
                and not _tem_texto_suficiente(doc, settings.ocr_min_chars_page)
            ):
                logger.info("texto residual, repetindo com OCR arquivo=%s", caminho.name)
                resultado = _converter_para(True).convert(str(caminho))
                doc = resultado.document
            dados = _exportar(doc)
            _ultimo_uso = time.monotonic()
        return dados
    except ConversionError:
        raise
    except Exception as exc:  # pragma: no cover - depende do ambiente
        raise ConversionError("Falha ao converter o documento") from exc


def segundos_ocioso() -> float | None:
    """Segundos desde a última conversão (None se nunca converteu)."""
    if _ultimo_uso is None:
        return None
    return time.monotonic() - _ultimo_uso


def _malloc_trim() -> None:
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def liberar(limite: float | None = None) -> bool:
    """Descarta os modelos carregados e devolve a memória ao SO.

    `limite` revalida a ociosidade já com o lock: uma conversão que terminou
    enquanto o monitor esperava não perde os modelos recém-carregados.
    """
    global _ultimo_uso
    with _lock:
        if limite is not None:
            ocioso = segundos_ocioso()
            if ocioso is None or ocioso < limite:
                return False
        if not _converters:
            _ultimo_uso = None
            return False
        _converters.clear()
        _ultimo_uso = None
    gc.collect()
    _malloc_trim()
    logger.info("modelos do Docling liberados por inatividade")
    return True
