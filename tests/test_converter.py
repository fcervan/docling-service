import sys
import types

import pytest

from app import converter as conv


class _Doc:
    def __init__(self, falha_tabelas=False):
        self._falha = falha_tabelas

    def export_to_markdown(self):
        return "# título"

    def export_to_dict(self):
        return {"texts": [{"text": "oi"}]}

    @property
    def tables(self):
        if self._falha:
            raise RuntimeError("sem tabelas")
        return [1, 2]


def _stub_docling(monkeypatch, doc=None, erro=False):
    doc_mod = types.ModuleType("docling")
    conv_mod = types.ModuleType("docling.document_converter")

    class DocumentConverter:
        def convert(self, _caminho):
            if erro:
                raise RuntimeError("pdf quebrado")
            return types.SimpleNamespace(document=doc or _Doc())

    conv_mod.DocumentConverter = DocumentConverter
    monkeypatch.setitem(sys.modules, "docling", doc_mod)
    monkeypatch.setitem(sys.modules, "docling.document_converter", conv_mod)


def test_converte_documento(tmp_path, monkeypatch):
    _stub_docling(monkeypatch)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    out = conv.converter(arq)
    assert out["document"] == {"texts": [{"text": "oi"}]}
    assert out["markdown"] == "# título"
    assert out["tabelas"] == 2


def test_tabelas_com_erro_viram_zero(tmp_path, monkeypatch):
    _stub_docling(monkeypatch, doc=_Doc(falha_tabelas=True))
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    assert conv.converter(arq)["tabelas"] == 0


def test_falha_de_conversao(tmp_path, monkeypatch):
    _stub_docling(monkeypatch, erro=True)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    with pytest.raises(conv.ConversionError):
        conv.converter(arq)


def test_docling_indisponivel(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "docling", None)
    monkeypatch.setitem(sys.modules, "docling.document_converter", None)
    with pytest.raises(conv.ConversionError):
        conv.converter(tmp_path / "a.pdf")


def test_versao_docling_sem_pacote(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    monkeypatch.setattr(
        conv,
        "version",
        lambda _nome: (_ for _ in ()).throw(PackageNotFoundError("docling")),
    )
    assert conv.versao_docling() == "desconhecida"
