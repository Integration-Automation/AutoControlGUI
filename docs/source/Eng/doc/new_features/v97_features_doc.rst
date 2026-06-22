Unicode Text Normalisation & Slugify
====================================

``fuzzy`` and ``search_index.tokenize`` only lowercase, and OCR
``find_text_matches`` only ``.lower()`` + substring — so ``"Café"`` (NFC) versus
``"Café"`` (NFD) versus OCR ``"cafe"`` compare unequal. This adds the
canonicalisation layer they should run before matching.

Pure standard library (``unicodedata`` / ``re``); imports no ``PySide6``. Every
function is pure (text in, text out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        normalize_text, deaccent, slugify, normalize_quotes, fold_whitespace,
    )

    normalize_text("CAFÉ  Menu")          # "café menu"  (NFKC + casefold + ws)
    deaccent("résumé")                     # "resume"
    slugify("Café Menu! 2026")             # "cafe-menu-2026"
    normalize_quotes("“Hi” — it’s…")       # '"Hi" - it\'s...'

``normalize_text`` applies a Unicode ``form`` (default ``NFKC``), optional
casefolding, and whitespace folding, so the same text in different code-point
forms compares equal. ``deaccent`` strips combining marks; ``fold_whitespace``
collapses runs to single spaces; ``normalize_quotes`` maps smart quotes, dashes,
ellipsis and NBSP to ASCII; ``slugify`` produces an ASCII slug (de-accent,
lowercase, join alphanumeric runs with a separator). Run ``normalize_text``
before fuzzy/search/OCR matching to make matches accent- and form-insensitive.

Executor commands
-----------------

``AC_normalize_text`` returns ``{text}`` (with optional ``form`` / ``casefold``
/ ``collapse_ws``); ``AC_slugify`` returns ``{slug}``. Both are exposed as MCP
tools (``ac_normalize_text`` / ``ac_slugify``) and as Script Builder commands
under **Data**.
