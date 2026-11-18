import sys
import types

import pytest

from app import config
from app import converter as conv


class _Item:
    def __init__(self, texto: str):
        self.text = texto


class _Doc:
    def __init__(self, texto="oi", paginas=1, falha_tabelas=False):
        self.texts = [_Item(texto)]
        self.pages = list(range(paginas))
        self._falha = falha_tabelas

    def export_to_markdown(self):
        return "# título"

    def export_to_dict(self):
        return {"texts": [{"text": item.text} for item in self.texts]}

    @property
    def tables(self):
        if self._falha:
            raise RuntimeError("sem tabelas")
        return [1, 2]


def _stub_docling(monkeypatch, docs=None, erro=False, criados=None):
    """Dubla o Docling; `docs` mapeia do_ocr -> documento devolvido."""
    docs = docs or {}

    class PdfPipelineOptions:
        def __init__(self):
            self.do_ocr = False
            self.do_table_structure = False

    class PdfFormatOption:
        def __init__(self, pipeline_options=None):
            self.pipeline_options = pipeline_options

    class DocumentConverter:
        def __init__(self, format_options=None):
            opcao = (format_options or {}).get(InputFormat.PDF)
            self.ocr = bool(getattr(opcao.pipeline_options, "do_ocr", False))
            if criados is not None:
                criados.append(self.ocr)

        def convert(self, _caminho):
            if erro:
                raise RuntimeError("pdf quebrado")
            return types.SimpleNamespace(document=docs.get(self.ocr) or _Doc())

    base_models = types.ModuleType("docling.datamodel.base_models")

    class InputFormat:
        PDF = "pdf"

    base_models.InputFormat = InputFormat
    pipeline = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline.PdfPipelineOptions = PdfPipelineOptions
    datamodel = types.ModuleType("docling.datamodel")
    datamodel.__path__ = []
    document_converter = types.ModuleType("docling.document_converter")
    document_converter.DocumentConverter = DocumentConverter
    document_converter.PdfFormatOption = PdfFormatOption
    raiz = types.ModuleType("docling")
    raiz.__path__ = []

    monkeypatch.setitem(sys.modules, "docling", raiz)
    monkeypatch.setitem(sys.modules, "docling.datamodel", datamodel)
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", base_models)
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter)


def test_converte_documento(tmp_path, monkeypatch):
    _stub_docling(monkeypatch)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    out = conv.converter(arq)
    assert out["document"] == {"texts": [{"text": "oi"}]}
    assert out["markdown"] == "# título"
    assert out["tabelas"] == 2


def test_tabelas_com_erro_viram_zero(tmp_path, monkeypatch):
    _stub_docling(monkeypatch, docs={False: _Doc(falha_tabelas=True)})
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


def test_converter_reaproveita_modelos(tmp_path, monkeypatch):
    criados = []
    _stub_docling(monkeypatch, criados=criados)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    conv.converter(arq)
    conv.converter(arq)
    assert criados == [False]


def test_ocr_auto_repete_com_texto_residual(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCLING_OCR_MODE", "auto")
    config.reset_settings()
    criados = []
    _stub_docling(
        monkeypatch,
        docs={False: _Doc(texto=""), True: _Doc(texto="texto extraído por ocr " * 5)},
        criados=criados,
    )
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    out = conv.converter(arq)
    assert criados == [False, True]
    assert out["document"]["texts"][0]["text"].startswith("texto extraído por ocr")


def test_ocr_auto_nao_repete_quando_ha_texto(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCLING_OCR_MODE", "auto")
    config.reset_settings()
    criados = []
    _stub_docling(monkeypatch, docs={False: _Doc(texto="texto normal " * 10)}, criados=criados)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    conv.converter(arq)
    assert criados == [False]


def test_ocr_auto_ignora_formatos_nao_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCLING_OCR_MODE", "auto")
    config.reset_settings()
    criados = []
    _stub_docling(monkeypatch, docs={False: _Doc(texto="")}, criados=criados)
    arq = tmp_path / "a.txt"
    arq.write_bytes(b"oi")
    conv.converter(arq)
    assert criados == [False]


def test_ocr_on_usa_ocr_desde_o_inicio(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCLING_OCR_MODE", "on")
    config.reset_settings()
    criados = []
    _stub_docling(monkeypatch, criados=criados)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    conv.converter(arq)
    assert criados == [True]


def test_liberar_sem_modelos():
    assert conv.liberar() is False


def test_liberar_descarta_modelos(tmp_path, monkeypatch):
    _stub_docling(monkeypatch)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    conv.converter(arq)
    assert conv.segundos_ocioso() is not None
    assert conv.liberar() is True
    assert conv.segundos_ocioso() is None
    assert conv._converters == {}


def test_paginas_com_erro_vira_um():
    class Ruim:
        @property
        def pages(self):
            raise RuntimeError("sem páginas")

    assert conv._paginas(Ruim()) == 1


def test_conversion_error_propagado(tmp_path, monkeypatch):
    def quebra(_ocr):
        raise conv.ConversionError("falhou")

    monkeypatch.setattr(conv, "_converter_para", quebra)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    with pytest.raises(conv.ConversionError):
        conv.converter(arq)


def test_liberar_tolera_malloc_trim_indisponivel(tmp_path, monkeypatch):
    _stub_docling(monkeypatch)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    conv.converter(arq)

    def sem_libc(_nome):
        raise OSError("sem libc")

    monkeypatch.setattr(conv.ctypes, "CDLL", sem_libc)
    assert conv.liberar() is True


def test_ocr_mode_invalido(monkeypatch):
    monkeypatch.setenv("DOCLING_OCR_MODE", "talvez")
    config.reset_settings()
    with pytest.raises(config.ConfigError):
        config.get_settings()


def test_liberar_com_limite_nao_recente(tmp_path, monkeypatch):
    _stub_docling(monkeypatch)
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF")
    conv.converter(arq)
    assert conv.liberar(limite=999) is False
    assert conv._converters != {}
