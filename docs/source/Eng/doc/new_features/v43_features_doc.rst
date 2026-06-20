Locale-Aware Number, Currency & Date Parsing
============================================

Text scraped from a localized UI or OCR rarely matches Python's ``float()``:
``"1.234,56"`` is twelve-hundred in ``de_DE`` but malformed to ``float``. These
helpers parse such strings — and format values back — using **Babel**'s CLDR
data, so flows can read and assert on numbers, currency, and dates across
locales.

``babel`` is an **optional** dependency (``pip install je_auto_control[locale]``)
imported lazily, so the package stays importable without it; the functions raise
a clear error only when called without Babel. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        parse_decimal, parse_number, format_decimal, format_currency,
        format_date)

    parse_decimal("1.234,56", locale="de_DE")    # -> 1234.56
    parse_number("1,234", locale="en_US")        # -> 1234

    format_decimal(1234.5, locale="en_US")       # -> "1,234.5"
    format_currency(1234.5, "USD", locale="en_US")   # -> "$1,234.50"
    format_date("2026-06-20", locale="de_DE", fmt="short")   # -> "20.06.26"

``format_date`` accepts an ISO ``YYYY-MM-DD`` string or a ``date`` object and a
``fmt`` of ``short`` / ``medium`` / ``long`` / ``full``. Parse + format
round-trip within a locale.

.. note::

   The functional path requires Babel; CI runs these tests under
   ``importorskip`` so they execute wherever Babel is installed and are skipped
   otherwise. The wiring/facade are always verified.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_parse_decimal``             ``{value}`` float from a locale decimal string.
``AC_parse_number``              ``{value}`` int from a locale integer string.
``AC_format_decimal``            ``{text}`` number formatted for a locale.
``AC_format_currency``           ``{text}`` currency (ISO 4217) for a locale.
``AC_format_date``               ``{text}`` ISO date formatted for a locale.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_parse_decimal`` /
``ac_parse_number`` / ``ac_format_decimal`` / ``ac_format_currency`` /
``ac_format_date``) and as Script Builder commands under **Data**.
