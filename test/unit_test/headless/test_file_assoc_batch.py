"""Headless tests for file-association lookup (pure normalize + injected resolver)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.file_assoc import file_association, normalize_ext


def test_normalize_ext_from_path():
    assert normalize_ext("report.pdf") == ".pdf"
    assert normalize_ext(r"C:\Users\me\report.PDF") == ".pdf"


def test_normalize_ext_from_bare_and_dotted():
    assert normalize_ext("pdf") == ".pdf"
    assert normalize_ext(".PDF") == ".pdf"


def test_normalize_ext_takes_last_extension():
    assert normalize_ext("archive.tar.gz") == ".gz"


def test_normalize_ext_rejects_empty_and_extensionless():
    for bad in ("", "   ", "folder/", "no_dot_here/"):
        with pytest.raises(ValueError):
            normalize_ext(bad)


def test_file_association_uses_injected_resolver():
    def fake_resolver(ext):
        assert ext == ".pdf"
        return {"command": "acro.exe \"%1\"", "exe": "acro.exe",
                "friendly": "Acrobat", "content_type": "application/pdf"}

    info = file_association("report.pdf", resolver=fake_resolver)
    assert info["ext"] == ".pdf"
    assert info["exe"] == "acro.exe"
    assert info["friendly"] == "Acrobat"
    assert info["content_type"] == "application/pdf"


def test_file_association_missing_fields_default_to_none():
    info = file_association(".xyz", resolver=lambda ext: {})
    assert info["ext"] == ".xyz"
    assert info["exe"] is None and info["friendly"] is None
    assert info["command"] is None and info["content_type"] is None


def test_file_association_normalizes_before_resolving():
    seen = {}

    def fake_resolver(ext):
        seen["ext"] = ext
        return {}

    file_association("DOC", resolver=fake_resolver)
    assert seen["ext"] == ".doc"


# --- wiring ---------------------------------------------------------------

def test_executor_pure_normalize_path():
    from je_auto_control.utils.executor.action_executor import _normalize_ext
    assert _normalize_ext("report.pdf") == {"ext": ".pdf"}


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_normalize_ext", "AC_file_association"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_normalize_ext", "ac_file_association"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_normalize_ext", "AC_file_association"} <= specs


def test_facade_exports():
    for name in ("normalize_ext", "file_association"):
        assert hasattr(ac, name) and name in ac.__all__
