"""Configuração por variáveis de ambiente.

Nenhum segredo é versionado: as chaves de API chegam apenas por env/secret
manager, e o serviço armazena somente o SHA-256 delas.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache

SUPPORTED = (".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm", ".xml", ".txt", ".md")

ALLOWED_MIMES = frozenset(
    {
        "",
        "application/octet-stream",
        "application/pdf",
        "application/csv",
        "application/xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "text/html",
        "text/markdown",
        "text/plain",
        "text/xml",
    }
)

DANGEROUS_MIMES = frozenset(
    {
        "application/x-dosexec",
        "application/x-elf",
        "application/x-executable",
        "application/x-msdownload",
        "application/x-sh",
        "application/x-shellscript",
    }
)


class ConfigError(RuntimeError):
    """Configuração inválida (sem expor valores sensíveis)."""


@dataclass(frozen=True)
class Settings:
    api_keys: dict[str, str]
    max_upload_mb: int
    convert_timeout: float
    rate_limit_per_minute: int
    schema_version: str

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def _parse_keys(raw: str) -> dict[str, str]:
    """Aceita JSON {"app": "sha256hex"} ou "app:sha256hex,app2:sha256hex"."""
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith(("{", "[")):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError("DOCLING_API_KEYS não é um JSON válido") from exc
        if not isinstance(data, dict):
            raise ConfigError("DOCLING_API_KEYS deve ser um objeto JSON {app: hash}")
        itens = data.items()
    elif ":" in raw:
        itens = (par.split(":", 1) for par in raw.split(",") if ":" in par)
    else:
        raise ConfigError("DOCLING_API_KEYS inválido: use JSON {app: hash} ou app:hash")
    chaves: dict[str, str] = {}
    for app, valor in itens:
        app = str(app).strip()
        valor = str(valor).strip().lower()
        if not app or not valor:
            continue
        if len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
            raise ConfigError(f"Hash inválido para o app '{app}': use SHA-256 em hexadecimal")
        chaves[app] = valor
    return chaves


def _int_env(nome: str, padrao: int, minimo: int = 0) -> int:
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except ValueError as exc:
        raise ConfigError(f"{nome} deve ser um inteiro") from exc
    return max(minimo, valor)


def _float_env(nome: str, padrao: float, minimo: float = 1.0) -> float:
    try:
        valor = float(os.getenv(nome, str(padrao)))
    except ValueError as exc:
        raise ConfigError(f"{nome} deve ser um número") from exc
    return max(minimo, valor)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        api_keys=_parse_keys(os.getenv("DOCLING_API_KEYS", "")),
        max_upload_mb=_int_env("DOCLING_MAX_UPLOAD_MB", 50, minimo=1),
        convert_timeout=_float_env("DOCLING_CONVERT_TIMEOUT", 300.0, minimo=0.1),
        rate_limit_per_minute=_int_env("DOCLING_RATE_LIMIT_PER_MINUTE", 60),
        schema_version=os.getenv("DOCLING_SCHEMA_VERSION", "1"),
    )


def reset_settings() -> None:
    """Invalida o cache (usado em testes e em rotação de chaves)."""
    get_settings.cache_clear()
