import json

import pytest
from fastapi import HTTPException

from app import auth, config
from tests.conftest import CHAVE_TESTE


def test_hash_key_estavel():
    assert auth.hash_key("abc") == auth.hash_key("abc")
    assert len(auth.hash_key("abc")) == 64
    assert auth.hash_key("abc") != auth.hash_key("abd")


def test_chave_valida_retorna_app():
    assert auth.verificar_api_key(CHAVE_TESTE) == "teste"


def test_chave_ausente_401():
    with pytest.raises(HTTPException) as exc:
        auth.verificar_api_key(None)
    assert exc.value.status_code == 401


def test_chave_invalida_401():
    with pytest.raises(HTTPException) as exc:
        auth.verificar_api_key("errada")
    assert exc.value.status_code == 401


def test_sem_chaves_configuradas_falha_fechado(monkeypatch):
    monkeypatch.delenv("DOCLING_API_KEYS", raising=False)
    config.reset_settings()
    with pytest.raises(HTTPException) as exc:
        auth.verificar_api_key("qualquer")
    assert exc.value.status_code == 503


def test_rate_limit_por_app(monkeypatch):
    monkeypatch.setenv("DOCLING_RATE_LIMIT_PER_MINUTE", "2")
    config.reset_settings()
    assert auth.verificar_api_key(CHAVE_TESTE) == "teste"
    assert auth.verificar_api_key(CHAVE_TESTE) == "teste"
    with pytest.raises(HTTPException) as exc:
        auth.verificar_api_key(CHAVE_TESTE)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_rate_limit_desligado(monkeypatch):
    monkeypatch.setenv("DOCLING_RATE_LIMIT_PER_MINUTE", "0")
    config.reset_settings()
    for _ in range(5):
        assert auth.verificar_api_key(CHAVE_TESTE) == "teste"


def test_parse_keys_json_e_texto():
    h = auth.hash_key("x")
    assert config._parse_keys(json.dumps({"a": h})) == {"a": h}
    assert config._parse_keys(f"a:{h}") == {"a": h}
    assert config._parse_keys("") == {}


def test_rate_limit_janela_expira(monkeypatch):
    tempos = iter([0.0, 61.0])
    monkeypatch.setattr(auth.time, "monotonic", lambda: next(tempos))
    monkeypatch.setenv("DOCLING_RATE_LIMIT_PER_MINUTE", "1")
    config.reset_settings()
    assert auth.verificar_api_key(CHAVE_TESTE) == "teste"
    assert auth.verificar_api_key(CHAVE_TESTE) == "teste"


def test_parse_keys_invalidas():
    with pytest.raises(config.ConfigError):
        config._parse_keys('{"a": "curto"}')
    with pytest.raises(config.ConfigError):
        config._parse_keys("{")
    with pytest.raises(config.ConfigError):
        config._parse_keys("nao-e-json")
    with pytest.raises(config.ConfigError):
        config._parse_keys("[1,2]")


def test_parse_keys_ignora_app_ou_hash_vazio():
    assert config._parse_keys('{"a": ""}') == {}
    assert config._parse_keys('{"": "abc"}') == {}


def test_settings_env_invalidas(monkeypatch):
    monkeypatch.setenv("DOCLING_MAX_UPLOAD_MB", "abc")
    config.reset_settings()
    with pytest.raises(config.ConfigError):
        config.get_settings()
    monkeypatch.setenv("DOCLING_MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("DOCLING_CONVERT_TIMEOUT", "abc")
    config.reset_settings()
    with pytest.raises(config.ConfigError):
        config.get_settings()
