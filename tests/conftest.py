import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, config  # noqa: E402

CHAVE_TESTE = "chave-de-teste-nao-usar-em-producao"


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("DOCLING_API_KEYS", json.dumps({"teste": auth.hash_key(CHAVE_TESTE)}))
    monkeypatch.setenv("DOCLING_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("DOCLING_MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("DOCLING_CONVERT_TIMEOUT", "5")
    config.reset_settings()
    auth.limiter.reset()
    yield
    config.reset_settings()
    auth.limiter.reset()
