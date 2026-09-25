"""Numeric line edits validate what int() and float() parse, in any locale.

Under French or German, QDoubleValidator refused "0.8" while typing and accepted
"0,8", which float() rejects: the Image Detect threshold could not be changed.
"""
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtGui import QValidator  # noqa: E402

from je_auto_control.gui._validators import double_validator, int_validator  # noqa: E402

_GUI = Path(__file__).resolve().parents[3] / "je_auto_control" / "gui"


@pytest.fixture()
def comma_locale():
    previous = QLocale()
    QLocale.setDefault(QLocale("de_DE"))
    yield
    QLocale.setDefault(previous)


@pytest.mark.usefixtures("comma_locale")
def test_a_decimal_point_is_accepted_and_a_comma_is_not():
    validator = double_validator(0.0, 1.0, 2)
    assert validator.validate("0.8", 0)[0] == QValidator.State.Acceptable
    assert validator.validate("0,8", 0)[0] != QValidator.State.Acceptable


@pytest.mark.usefixtures("comma_locale")
def test_a_group_separator_is_not_an_integer():
    validator = int_validator(1, 10_000)
    assert validator.validate("1000", 0)[0] == QValidator.State.Acceptable
    assert validator.validate("1.000", 0)[0] != QValidator.State.Acceptable


def test_every_numeric_line_edit_uses_the_helper():
    raw = re.compile(r"\bQ(?:Int|Double)Validator\(")
    offenders = [str(path.relative_to(_GUI)) for path in _GUI.rglob("*.py")
                 if path.name != "_validators.py" and raw.search(path.read_text(encoding="utf-8"))]
    assert offenders == []
