GNU gettext Catalog I/O (.po / .mo)
===================================

The repo has ``i18n_test`` (pseudo-localisation, catalog placeholder checks) and
``message_format`` (ICU rendering) but no reader for the *de-facto* translation
format — GNU gettext ``.po`` / ``.mo``. This parses ``.po`` text (contexts,
plurals, multi-line strings, escapes, the ``Plural-Forms`` header), compiles the
binary ``.mo`` (the same little-endian format Python's own ``gettext`` reads) and
exposes ``gettext`` / ``ngettext`` / ``pgettext`` lookups.

Pure standard library (``re`` / ``struct`` / ``gettext.c2py`` for the plural
expression); imports no ``PySide6``. Parsing and compilation are pure data
in / data out, so they are fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import parse_po, read_mo, GettextCatalog

    catalog = parse_po(po_text)
    catalog.gettext("Hello")                 # 'Hola'
    catalog.ngettext("file", "files", 3)     # 'archivos'
    catalog.pgettext("menu", "Open")         # 'Abrir'

    mo_bytes = catalog.compile_mo("out/messages.mo")   # or .to_mo_bytes()
    same = read_mo(mo_bytes)                  # round-trips, incl. plural rules

    # build one by hand
    cat = GettextCatalog()
    cat.add("apple", ["pomme", "pommes"], plural_id="apples")

``gettext`` returns the translation (or the source ``msgid`` when untranslated);
``ngettext`` evaluates the catalog's ``Plural-Forms`` expression (via
``gettext.c2py``) to pick the right form for ``n``; ``pgettext`` adds a
disambiguation context. ``to_mo_bytes`` / ``compile_mo`` emit a standards-
compliant ``.mo`` that Python's own ``gettext.GNUTranslations`` can load, and
``read_mo`` / ``read_mo_file`` parse one back (little- or big-endian).

Executor commands
-----------------

``AC_gettext_translate`` parses an inline ``.po`` string and returns ``{text}``
for a ``msgid`` (optional ``context``); ``AC_gettext_ngettext`` returns the
plural-correct ``{text}`` for a count ``n``. Both are exposed as MCP tools
(``ac_gettext_translate`` / ``ac_gettext_ngettext``) and as Script Builder
commands under **Data**.
