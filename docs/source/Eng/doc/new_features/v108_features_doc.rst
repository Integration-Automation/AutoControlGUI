Locale-Aware String Collation
=============================

``text_normalize`` canonicalises text and ``locale_parse`` formats numbers, but
nothing sorts strings the way a reader of a given language expects. Python's
default ``sorted`` is codepoint order, so ``"Z" < "a"`` and ``"ä"`` lands far
from ``"a"``. A real collation orders by *base letter* first, then *accent*,
then *case*, and lets a locale tailor the alphabet (Swedish sorts ``å ä ö`` after
``z``).

This builds a Unicode-Collation-lite sort key with three levels — primary (base
letter), secondary (diacritics), tertiary (case) — plus an optional alphabet
``tailoring``. Pure standard library (``unicodedata``); imports no ``PySide6``.
Every function is pure, so it is fully deterministic across platforms (unlike
``locale.strxfrm``, which depends on the host's installed locales).

Headless API
------------

.. code-block:: python

    from je_auto_control import sort_strings, collation_compare, collation_key

    sort_strings(["résumé", "rest", "resume"])
    # ['rest', 'resume', 'résumé']   (accent is a secondary difference)

    swedish = "abcdefghijklmnopqrstuvwxyzåäö"
    sort_strings(["zebra", "äpple", "apple"], tailoring=swedish)
    # ['apple', 'zebra', 'äpple']    (å ä ö sort after z)

    collation_compare("apple", "Apple")        # -1  (lowercase before uppercase)
    sort_strings(rows, key=lambda r: r["name"])  # sort dicts by a field

``strength`` (``primary`` / ``secondary`` / ``tertiary``) caps the levels
compared, so ``strength="primary"`` is accent- and case-insensitive.
``tailoring`` is an ordered alphabet whose characters sort in the given order and
before any unlisted character; a precomposed letter such as ``"å"`` keeps its
alphabet rank instead of decomposing to ``a`` + diaeresis. ``collation_key``
returns the raw comparable tuple for use as a ``sorted`` key.

Executor commands
-----------------

``AC_collation_sort`` takes a JSON list and returns ``{sorted}``;
``AC_collation_compare`` returns ``{order: -1|0|1}``. Both accept ``strength``
and ``tailoring``, are exposed as MCP tools (``ac_collation_sort`` /
``ac_collation_compare``) and as Script Builder commands under **Data**.
