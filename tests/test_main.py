import asyncio
import time

import httpx
import pytest

from app import config, main
from app.converter import ConversionError
from tests.conftest import CHAVE_TESTE

HEADERS = {"X-API-Key": CHAVE_TESTE}


def _req(metodo: str, path: str, **kwargs):
    async def rodar():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://teste") as cliente:
            return await cliente.request(metodo, path, **kwargs)

    return asyncio.run(rodar())


def _pdf(nome: str = "a.pdf", conteudo: bytes = b"%PDF-1.4 teste"):
    return {"file": (nome, conteudo, "application/pdf")}


def _fake_converter(caminho):
    texto = caminho.read_text(encoding="utf-8", errors="ignore")
    return {
        "document": {"texts": [{"text": texto}]},
        "markdown": f"# {caminho.name}",
        "tabelas": 2,
    }


def test_health_sem_auth():
    r = _req("GET", "/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_info_sem_segredos():
    r = _req("GET", "/v1/info")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["service"] == "docling-service"
    assert ".pdf" in corpo["supported_extensions"]
    assert corpo["ocr_mode"] == "off"
    assert corpo["idle_unload_seconds"] == 900
    assert "api_keys" not in corpo


def test_convert_sucesso(monkeypatch):
    monkeypatch.setattr(main, "converter", _fake_converter)
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf())
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["filename"] == "a.pdf"
    assert corpo["tabelas"] == 2
    assert corpo["schema_version"] == "1"
    assert corpo["markdown"] == "# a.pdf"
    assert corpo["document"]["texts"][0]["text"].startswith("%PDF")


def test_convert_sanitiza_nome(monkeypatch):
    monkeypatch.setattr(main, "converter", _fake_converter)
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf("../../evil.pdf"))
    assert r.status_code == 200 and r.json()["filename"] == "evil.pdf"


def test_convert_sem_chave_401():
    r = _req("POST", "/v1/convert", files=_pdf())
    assert r.status_code == 401


def test_convert_chave_invalida_401():
    r = _req("POST", "/v1/convert", headers={"X-API-Key": "nope"}, files=_pdf())
    assert r.status_code == 401


def test_convert_sem_chaves_503(monkeypatch):
    monkeypatch.delenv("DOCLING_API_KEYS", raising=False)
    config.reset_settings()
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf())
    assert r.status_code == 503


def test_convert_extensao_nao_suportada():
    r = _req(
        "POST",
        "/v1/convert",
        headers=HEADERS,
        files={"file": ("virus.exe", b"MZ", "application/pdf")},
    )
    assert r.status_code == 415


def test_convert_mime_perigoso():
    r = _req(
        "POST",
        "/v1/convert",
        headers=HEADERS,
        files={"file": ("a.pdf", b"%PDF", "application/x-msdownload")},
    )
    assert r.status_code == 415


def test_convert_mime_desconhecido():
    r = _req(
        "POST",
        "/v1/convert",
        headers=HEADERS,
        files={"file": ("a.pdf", b"%PDF", "application/x-custom")},
    )
    assert r.status_code == 415


def test_nome_seguro_invalido():
    assert main._nome_seguro(None) == ""
    assert main._nome_seguro("..") == ""
    assert main._nome_seguro(".pdf") == ".pdf"


def test_convert_nome_invalido_400():
    r = _req(
        "POST",
        "/v1/convert",
        headers=HEADERS,
        files={"file": ("..", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 400


def test_convert_arquivo_vazio():
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf(conteudo=b""))
    assert r.status_code == 400


def test_convert_arquivo_grande():
    grande = b"x" * (1024 * 1024 + 1)
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf(conteudo=grande))
    assert r.status_code == 413


def test_convert_erro_de_conversao(monkeypatch):
    def quebra(_caminho):
        raise ConversionError("falhou")

    monkeypatch.setattr(main, "converter", quebra)
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf())
    assert r.status_code == 422
    assert "falhou" not in r.text


def test_convert_erro_inesperado(monkeypatch):
    def quebra(_caminho):
        raise RuntimeError("stack secreto")

    monkeypatch.setattr(main, "converter", quebra)
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf())
    assert r.status_code == 500
    assert "stack secreto" not in r.text


def test_convert_timeout(monkeypatch):
    def lento(_caminho):
        time.sleep(0.4)
        return {"document": {}, "markdown": "", "tabelas": 0}

    monkeypatch.setattr(main, "converter", lento)
    monkeypatch.setenv("DOCLING_CONVERT_TIMEOUT", "0.1")
    config.reset_settings()
    r = _req("POST", "/v1/convert", headers=HEADERS, files=_pdf())
    assert r.status_code == 504


def test_monitor_idle_libera_modelos(monkeypatch):
    monkeypatch.setenv("DOCLING_IDLE_UNLOAD_SECONDS", "60")
    config.reset_settings()
    chamadas = []
    monkeypatch.setattr(main.converter_mod, "segundos_ocioso", lambda: 120)
    monkeypatch.setattr(main.converter_mod, "liberar", lambda *args: chamadas.append(True))
    estado = {"n": 0}

    def dorme(_segundos):
        estado["n"] += 1
        if estado["n"] > 1:
            raise SystemExit

    monkeypatch.setattr(main.time, "sleep", dorme)
    with pytest.raises(SystemExit):
        main._monitor_idle()
    assert chamadas == [True]


def test_monitor_idle_desligado(monkeypatch):
    monkeypatch.setenv("DOCLING_IDLE_UNLOAD_SECONDS", "0")
    config.reset_settings()
    chamadas = []
    monkeypatch.setattr(main.converter_mod, "segundos_ocioso", lambda: 999)
    monkeypatch.setattr(main.converter_mod, "liberar", lambda *args: chamadas.append(True))
    estado = {"n": 0}

    def dorme(_segundos):
        estado["n"] += 1
        if estado["n"] > 1:
            raise SystemExit

    monkeypatch.setattr(main.time, "sleep", dorme)
    with pytest.raises(SystemExit):
        main._monitor_idle()
    assert chamadas == []


def test_lifespan_inicia_monitor(monkeypatch):
    monkeypatch.setenv("DOCLING_IDLE_UNLOAD_SECONDS", "60")
    config.reset_settings()
    iniciados = []

    class ThreadFalsa:
        def __init__(self, target=None, name=None, daemon=None):
            self.target, self.name, self.daemon = target, name, daemon

        def start(self):
            iniciados.append(self.name)

    monkeypatch.setattr(main.threading, "Thread", ThreadFalsa)

    async def rodar():
        async with main._lifespan(main.app):
            pass

    asyncio.run(rodar())
    assert iniciados == ["idle-unload"]


def test_lifespan_sem_monitor(monkeypatch):
    monkeypatch.setenv("DOCLING_IDLE_UNLOAD_SECONDS", "0")
    config.reset_settings()
    iniciados = []

    class ThreadFalsa:
        def __init__(self, *args, **kwargs):
            iniciados.append(True)

    monkeypatch.setattr(main.threading, "Thread", ThreadFalsa)

    async def rodar():
        async with main._lifespan(main.app):
            pass

    asyncio.run(rodar())
    assert iniciados == []
