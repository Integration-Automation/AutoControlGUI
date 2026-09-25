"""Numeric line-edit validators that accept what ``int()`` and ``float()`` parse.

``QIntValidator`` and ``QDoubleValidator`` validate in the default locale. Under
French or German that is a decimal comma: "0.8" was refused while typing and
"0,8" accepted, which ``float()`` then rejects, so a decimal could not be
entered at all. These validate in the C locale, as the parsers read.
"""
from typing import Optional

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator, QIntValidator


def int_validator(bottom: Optional[float] = None, top: Optional[float] = None) -> QIntValidator:
    """A ``QIntValidator`` in the C locale, bounded where ``bottom`` / ``top`` are given."""
    validator = QIntValidator()
    if bottom is not None:
        validator.setBottom(int(bottom))
    if top is not None:
        validator.setTop(int(top))
    validator.setLocale(QLocale.c())
    return validator


def double_validator(bottom: float, top: float, decimals: int) -> QDoubleValidator:
    """A ``QDoubleValidator`` in the C locale."""
    validator = QDoubleValidator(bottom, top, decimals)
    validator.setLocale(QLocale.c())
    return validator
