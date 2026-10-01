"""A compiled .mo leaves untranslated entries out, as GNU msgfmt does.

Written with an empty translation, Python's own ``gettext`` (and any other
``.mo`` reader) returned ``""`` for the message instead of its ``msgid``.
"""
import gettext
import io

from je_auto_control.utils.gettext_catalog.gettext_catalog import parse_po, read_mo

PO = """msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

msgid "Save"
msgstr "Guardar"

msgid "Cancel"
msgstr ""

msgctxt "menu"
msgid "Open"
msgstr ""

msgid "file"
msgid_plural "files"
msgstr[0] ""
msgstr[1] ""

msgid "item"
msgid_plural "items"
msgstr[0] "elemento"
msgstr[1] "elementos"
"""


def _stdlib(catalog):
    return gettext.GNUTranslations(io.BytesIO(catalog.to_mo_bytes()))


def test_an_untranslated_entry_falls_back_to_its_msgid_in_any_mo_reader():
    catalog = parse_po(PO)
    stdlib = _stdlib(catalog)
    assert stdlib.gettext("Cancel") == "Cancel"
    assert stdlib.pgettext("menu", "Open") == "Open"
    assert stdlib.ngettext("file", "files", 2) == "files"
    assert read_mo(catalog.to_mo_bytes()).gettext("Cancel") == "Cancel"


def test_translated_entries_and_the_header_are_still_written():
    catalog = parse_po(PO)
    stdlib = _stdlib(catalog)
    assert stdlib.gettext("Save") == "Guardar"
    assert stdlib.ngettext("item", "items", 1) == "elemento"
    assert stdlib.ngettext("item", "items", 3) == "elementos"
    assert stdlib.info()["plural-forms"].startswith("nplurals=2")
    assert read_mo(catalog.to_mo_bytes()).ngettext("item", "items", 3) == "elementos"
