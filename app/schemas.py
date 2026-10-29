"""Contrato público do serviço."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConvertResponse(BaseModel):
    schema_version: str = Field(description="Versão do contrato de resposta")
    docling_version: str = Field(description="Versão do Docling usada na conversão")
    filename: str = Field(description="Nome do arquivo recebido (sanitizado)")
    tabelas: int = Field(ge=0, description="Quantidade de tabelas detectadas")
    markdown: str = Field(description="Documento em Markdown")
    document: dict[str, Any] = Field(description="Documento no formato export_to_dict() do Docling")


class InfoResponse(BaseModel):
    service: str
    schema_version: str
    docling_version: str
    supported_extensions: list[str]
    max_upload_mb: int
    convert_timeout_seconds: float


class HealthResponse(BaseModel):
    ok: bool
