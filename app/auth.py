"""Autenticação por API key (hash SHA-256 + rate limit por aplicação)."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict

from fastapi import Header, HTTPException

from .config import get_settings


def hash_key(chave: str) -> str:
    return hashlib.sha256((chave or "").encode("utf-8")).hexdigest()


class RateLimiter:
    """Janela deslizante em memória (uma instância por processo)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def checar(self, app: str, limite: int) -> None:
        if limite <= 0:
            return
        agora = time.monotonic()
        with self._lock:
            janela = self._hits[app]
            while janela and agora - janela[0] >= 60.0:
                janela.pop(0)
            if len(janela) >= limite:
                espera = max(1, int(60.0 - (agora - janela[0])) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Limite de requisições excedido",
                    headers={"Retry-After": str(espera)},
                )
            janela.append(agora)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def verificar_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """Retorna o nome da aplicação autenticada ou levanta 401/429/503."""
    settings = get_settings()
    if not settings.api_keys:
        raise HTTPException(status_code=503, detail="Autenticação não configurada no serviço")
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key ausente",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
    candidato = hash_key(x_api_key)
    for app, esperado in settings.api_keys.items():
        if hmac.compare_digest(candidato, esperado):
            limiter.checar(app, settings.rate_limit_per_minute)
            return app
    raise HTTPException(
        status_code=401,
        detail="API key inválida",
        headers={"WWW-Authenticate": "X-API-Key"},
    )
