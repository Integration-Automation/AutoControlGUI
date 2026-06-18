"""Headless tests for PDF text extraction and assertion.

The single ``_open_pdf`` seam is monkeypatched with a fake reader, so the
tests need neither the optional pypdf package nor a real PDF file.
"""
import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlAssertionException
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_control import exec_pdf_to_var
from je_auto_control.utils.pdf import pdf_reader


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, pages, metadata=None):
        self.pages = [_FakePage(t) for t in pages]
        self.metadata = metadata or {}


@pytest.fixture()
def fake_pdf(monkeypatch):
    reader = _FakeReader(
        ["Invoice 123\nAmount due", "Total: $50.00", "Thank you"],
        metadata={"/Title": "Inv", "/Author": "Acme"})
    monkeypatch.setattr(pdf_reader, "_open_pdf", lambda _path: reader)
    return reader


def test_extract_all_pages(fake_pdf):
    text = pdf_reader.extract_pdf_text("x.pdf")
    assert "Invoice 123" in text
    assert "Total: $50.00" in text
    assert "Thank you" in text


def test_extract_single_page(fake_pdf):
    assert pdf_reader.extract_pdf_text("x.pdf", pages=2) == "Total: $50.00"


def test_extract_page_out_of_range(fake_pdf):
    with pytest.raises(ValueError):
        pdf_reader.extract_pdf_text("x.pdf", pages=9)


def test_page_count_and_metadata(fake_pdf):
    assert pdf_reader.pdf_page_count("x.pdf") == 3
    meta = pdf_reader.pdf_metadata("x.pdf")
    assert meta == {"Title": "Inv", "Author": "Acme"}


def test_assert_present_passes(fake_pdf):
    result = pdf_reader.assert_pdf_text("x.pdf", "Invoice 123")
    assert result["passed"] is True


def test_assert_absent_passes(fake_pdf):
    result = pdf_reader.assert_pdf_text("x.pdf", "Refund", present=False)
    assert result["passed"] is True


def test_assert_present_fails_raises(fake_pdf):
    with pytest.raises(AutoControlAssertionException):
        pdf_reader.assert_pdf_text("x.pdf", "Nonexistent")


def test_assert_no_raise_returns_false(fake_pdf):
    result = pdf_reader.assert_pdf_text("x.pdf", "Nope", raise_on_fail=False)
    assert result["passed"] is False


def test_assert_case_insensitive(fake_pdf):
    result = pdf_reader.assert_pdf_text("x.pdf", "invoice 123",
                                        case_sensitive=False)
    assert result["passed"] is True


def test_assert_on_specific_page(fake_pdf):
    ok = pdf_reader.assert_pdf_text("x.pdf", "Total", page=2)
    assert ok["passed"] is True
    with pytest.raises(AutoControlAssertionException):
        pdf_reader.assert_pdf_text("x.pdf", "Total", page=1)


def test_pdf_to_var_flow(fake_pdf):
    executor = Executor()
    result = exec_pdf_to_var(executor, {"path": "x.pdf", "var": "doc", "page": 1})
    assert result["var"] == "doc"
    assert executor.variables.get_value("doc") == "Invoice 123\nAmount due"


def test_missing_pypdf_raises_runtimeerror(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError):
        pdf_reader._open_pdf("x.pdf")


def test_facade_executor_and_mcp_wiring(fake_pdf):
    assert ac.assert_pdf_text is pdf_reader.assert_pdf_text
    assert ac.extract_pdf_text is pdf_reader.extract_pdf_text
    known = ac.executor.known_commands()
    assert {"AC_assert_pdf_text", "AC_pdf_to_var"} <= known
    record = ac.execute_action(
        [["AC_assert_pdf_text", {"path": "x.pdf", "text": "Invoice 123"}]])
    assert any("passed" in str(value) or "pdf_text" in str(value)
               for value in record.values())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_extract_pdf_text", "ac_assert_pdf_text"} <= names
