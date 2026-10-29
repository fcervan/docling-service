#!/usr/bin/env python3
"""Gera uma API key forte e o hash SHA-256 correspondente.

A key em texto puro deve ir SOMENTE para o app consumidor (env/secret manager).
O hash é o que vai para DOCLING_API_KEYS no serviço.
"""

from __future__ import annotations

import hashlib
import json
import secrets


def main() -> None:
    app = input("Nome da aplicação (ex: assistente-suporte): ").strip() or "app"
    chave = secrets.token_urlsafe(32)
    digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()
    print("\nGuarde a API key apenas no app consumidor (nunca no Git):")
    print(f"  DOCLING_API_KEY={chave}")
    print("\nConfigure o hash no serviço:")
    print(f"  DOCLING_API_KEYS={json.dumps({app: digest})}")


if __name__ == "__main__":
    main()
