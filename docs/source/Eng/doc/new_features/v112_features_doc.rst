Locale-Aware List Formatting
============================

``locale_parse`` formats numbers and dates, but joining a list of items the way a
language expects — the conjunction word, whether there is a serial/Oxford comma,
the two-item special case — is its own small problem. A naive ``", ".join`` gives
``"A, B, C"`` with no "and"/"or" and no localisation.

This implements the CLDR list-pattern composition (start/middle/end plus a
two-item pattern) for a handful of locales and the conjunction / disjunction /
unit styles. Pure standard library; imports no ``PySide6``. Every function is
pure, so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import format_list

    format_list(["apple", "pear", "grape"])               # 'apple, pear, and grape'
    format_list(["apple", "pear", "grape"], style="or")   # 'apple, pear, or grape'
    format_list(["apple", "pear"], style="unit")          # 'apple, pear'
    format_list(["manzana", "pera", "uva"], locale="es")  # 'manzana, pera y uva'
    format_list(["A", "B", "C", "D"], locale="fr")        # 'A, B, C et D'

``style`` is ``"and"`` (conjunction), ``"or"`` (disjunction) or ``"unit"``
(comma-separated, no conjunction). ``locale`` selects the conjunction word and
the serial-comma rule (``en`` / ``es`` / ``fr`` / ``de`` / ``pt``; English uses
the Oxford comma, the others do not; an unknown locale falls back to English).
One and two element lists, and the empty list, are handled as special cases.
``ValueError`` is raised for an unknown ``style``.

Executor commands
-----------------

``AC_format_list`` takes a JSON array and returns ``{text}``, accepting ``style``
and ``locale``. It is exposed as the MCP tool ``ac_format_list`` and as a Script
Builder command under **Data**.
