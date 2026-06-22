"""Headless tests for GNU gettext catalog I/O. No Qt."""
import io
from gettext import GNUTranslations

import pytest

import je_auto_control as ac
from je_auto_control.utils.gettext_catalog import (
    GettextCatalog, parse_po, read_mo,
)

# Build a .po source. Continuation header lines carry a literal "\n" escape.
_PO = "\n".join([
    'msgid ""',
    'msgstr ""',
    '"Content-Type: text/plain; charset=UTF-8\\n"',
    '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"',
    '',
    'msgid "Hello"',
    'msgstr "Hola"',
    '',
    'msgid "file"',
    'msgid_plural "files"',
    'msgstr[0] "archivo"',
    'msgstr[1] "archivos"',
    '',
    'msgctxt "menu"',
    'msgid "Open"',
    'msgstr "Abrir"',
    '',
])


def test_parse_singular_and_fallback():
    catalog = parse_po(_PO)
    assert catalog.gettext("Hello") == "Hola"
    assert catalog.gettext("Missing") == "Missing"      # untranslated -> id


def test_parse_plural():
    catalog = parse_po(_PO)
    assert catalog.ngettext("file", "files", 1) == "archivo"
    assert catalog.ngettext("file", "files", 4) == "archivos"
    assert catalog.ngettext("dog", "dogs", 2) == "dogs"   # missing -> english


def test_context():
    catalog = parse_po(_PO)
    assert catalog.pgettext("menu", "Open") == "Abrir"
    assert catalog.gettext("Open") == "Open"             # no ctx -> untranslated


def test_header_metadata_and_plural_forms():
    catalog = parse_po(_PO)
    assert catalog.metadata["Content-Type"] == "text/plain; charset=UTF-8"
    assert catalog.nplurals == 2


def test_mo_round_trip():
    catalog = parse_po(_PO)
    restored = read_mo(catalog.to_mo_bytes())
    assert restored.gettext("Hello") == "Hola"
    assert restored.ngettext("file", "files", 2) == "archivos"
    assert restored.pgettext("menu", "Open") == "Abrir"


def test_mo_is_readable_by_stdlib_gettext():
    catalog = parse_po(_PO)
    translations = GNUTranslations(io.BytesIO(catalog.to_mo_bytes()))
    assert translations.gettext("Hello") == "Hola"
    assert translations.ngettext("file", "files", 5) == "archivos"


def test_read_mo_rejects_bad_magic():
    with pytest.raises(ValueError):
        read_mo(b"not a mo file at all")


def test_build_programmatically():
    catalog = GettextCatalog()
    catalog.add("Yes", "Oui")
    catalog.add("apple", ["pomme", "pommes"], plural_id="apples")
    assert catalog.gettext("Yes") == "Oui"
    assert catalog.ngettext("apple", "apples", 2) == "pommes"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_gettext_translate", {"po": _PO, "msgid": "Hello"}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["text"] == "Hola"
    rec2 = ac.execute_action([[
        "AC_gettext_ngettext",
        {"po": _PO, "msgid": "file", "msgid_plural": "files", "n": 3}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["text"] == "archivos"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_gettext_translate", "AC_gettext_ngettext"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_gettext_translate", "ac_gettext_ngettext"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_gettext_translate", "AC_gettext_ngettext"} <= specs


def test_facade_exports():
    for attr in ("GettextCatalog", "parse_po", "parse_po_file", "read_mo",
                 "read_mo_file"):
        assert hasattr(ac, attr) and attr in ac.__all__
