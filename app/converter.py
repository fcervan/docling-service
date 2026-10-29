"""Wrapper fino em volta do Docling (import lazy para testes e startup leve)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


class ConversionError(Exception):
    """Falha de conversão (mensagem segura para o cliente)."""


def versao_docling() -> str:
    try:
        return version("docling")
    except PackageNotFoundError:
        return "desconhecida"


def converter(caminho: Path) -> dict:
    """Converte um arquivo local e devolve document/markdown/tabelas."""
    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:  # pragma: no cover - depende do ambiente
        raise ConversionError("Docling indisponível no serviço") from exc

    try:
        result = DocumentConverter().convert(str(caminho))
        doc = result.document
        document = doc.export_to_dict()
        markdown = doc.export_to_markdown()
        try:
            tabelas = len(doc.tables or [])
        except Exception:
            tabelas = 0
        return {"document": document, "markdown": markdown, "tabelas": tabelas}
    except Exception as exc:
        raise ConversionError("Falha ao converter o documento") from exc
