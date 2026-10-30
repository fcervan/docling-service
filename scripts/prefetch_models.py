#!/usr/bin/env python3
"""Pré-baixa os modelos do Docling e do OCR usados em runtime."""

from __future__ import annotations

from pathlib import Path

from docling.document_converter import DocumentConverter
from PIL import Image, ImageDraw


def main() -> None:
    converter = DocumentConverter()
    converter.convert("assets/prefetch.pdf")

    imagem = Image.new("RGB", (900, 400), "white")
    ImageDraw.Draw(imagem).text((60, 180), "OCR prefetch 12345", fill="black")
    amostra = Path("/tmp/ocr-prefetch.pdf")
    imagem.save(amostra, "PDF")
    try:
        converter.convert(str(amostra))
    finally:
        amostra.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
