"""Parse and format numbers, currency, and dates the way a locale writes them.

Text scraped from a localized UI or OCR rarely matches Python's ``float()``:
``"1.234,56"`` is twelve-hundred in ``de_DE`` but malformed to ``float``. These
helpers parse such strings (and format values back) using **Babel**'s CLDR data,
so flows can read and assert on numbers/currency/dates across locales.

``babel`` is an **optional** dependency (``pip install je_auto_control[locale]``);
it is imported lazily, so the package stays importable without it and the
functions raise a clear error only when actually called without Babel installed.
Imports no ``PySide6``.
"""
import datetime
from typing import Any, Union


def _numbers() -> Any:
    try:
        from babel import numbers
    except ImportError as error:  # pragma: no cover - exercised without babel
        raise RuntimeError(
            "locale parsing requires Babel: pip install "
            "je_auto_control[locale]") from error
    return numbers


def parse_decimal(text: str, locale: str = "en_US") -> float:
    """Parse a locale-formatted decimal string into a ``float``."""
    return float(_numbers().parse_decimal(text, locale=locale))


def parse_number(text: str, locale: str = "en_US") -> int:
    """Parse a locale-formatted integer string into an ``int``."""
    return int(_numbers().parse_decimal(text, locale=locale))


def format_decimal(value: Union[int, float], locale: str = "en_US") -> str:
    """Format a number the way ``locale`` writes decimals."""
    return _numbers().format_decimal(value, locale=locale)


def format_currency(value: Union[int, float], currency: str,
                    locale: str = "en_US") -> str:
    """Format ``value`` as ``currency`` (ISO 4217) for ``locale``."""
    return _numbers().format_currency(value, currency, locale=locale)


def format_date(value: Union[str, datetime.date], locale: str = "en_US",
                fmt: str = "medium") -> str:
    """Format a date (or ISO ``YYYY-MM-DD`` string) for ``locale``."""
    try:
        from babel.dates import format_date as _format_date
    except ImportError as error:  # pragma: no cover - exercised without babel
        raise RuntimeError(
            "locale formatting requires Babel: pip install "
            "je_auto_control[locale]") from error
    date_value = (datetime.date.fromisoformat(value)
                  if isinstance(value, str) else value)
    return _format_date(date_value, format=fmt, locale=locale)
