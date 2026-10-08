"""Rules the GUI tests themselves have to keep (offscreen Qt for the helper; the rest reads source).

* No test finds its widgets by scanning ``QApplication.topLevelWidgets()``. PySide builds that list one
  element at a time; on Python 3.10 / 3.11 an allocation in the middle can run the cycle collector,
  which destroys window garbage whose pointers are still in the list (the 3.10 segfault of
  ``test_usb_acl_prompt``). A test records the widgets it makes, or asks Qt for one pointer.
* A test that builds a parentless panel deletes it: ``_qt_settle.deleting`` does that for a module.
"""
import os
import pathlib
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QVBoxLayout, QWidget  # noqa: E402
from shiboken6 import Shiboken  # noqa: E402

from headless._qt_settle import deleting  # noqa: E402

_HERE = pathlib.Path(__file__).resolve().parent
_SCAN = re.compile(r"topLevelWidgets\s*\(")
#: Mentions in prose are written ``QApplication.topLevelWidgets()``, in double backticks.
_PROSE = re.compile(r"``[^`]*topLevelWidgets\(\)[^`]*``")
#: The one file that needs the call: it replaces the scan to prove what a collection inside it does.
_ALLOWED = {"test_usb_prompt_lifetime.py", pathlib.Path(__file__).name}


def _scans(path):
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        code = _PROSE.sub("", line)
        if _SCAN.search(code) and not code.lstrip().startswith("#"):
            found.append(f"{path.name}:{number}")
    return found


def test_no_test_scans_the_top_level_widgets():
    files = sorted(_HERE.glob("test_*.py")) + sorted(_HERE.glob("_*.py")) + [_HERE / "conftest.py"]
    assert len(files) > 100
    found = [hit for path in files if path.name not in _ALLOWED for hit in _scans(path)]
    assert found == [], f"record the widgets a test makes instead of scanning for them: {found}"


def test_the_scan_rule_sees_code_and_ignores_prose(tmp_path):
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        '"""Never ``QApplication.topLevelWidgets()`` here."""\n'
        "# QApplication.topLevelWidgets() is unsafe\n"
        "found = [w for w in QApplication.topLevelWidgets() if w.isVisible()]\n"
        "probe = '''\n"
        "overlays = QApplication.topLevelWidgets ()\n"
        "'''\n", encoding="utf-8")
    assert _scans(sample) == ["test_sample.py:3", "test_sample.py:5"]


class _Panel(QWidget):
    """A parentless panel with a combo box and a slot that closes over it, as the real ones have."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        self.combo.addItems(["one", "two"])
        self.combo.view()                   # makes the popup container, a top-level child of the combo
        layout.addWidget(self.combo)
        self.combo.currentIndexChanged.connect(lambda index: self.setWindowTitle(str(index)))


class _Child(_Panel):
    """Inherits ``__init__``: the helper must give the class back without one of its own."""


def test_deleting_records_what_a_block_builds_and_deletes_it():
    app = QApplication.instance() or QApplication([])
    with deleting(_Panel, _Child) as made:
        first, second = _Panel(), _Child()
        nested = QWidget(first)
        assert made[:2] == [first, second]
    assert "__init__" not in vars(_Child), "an inherited __init__ was left overridden"
    assert Shiboken.isValid(first) and Shiboken.isValid(second)     # scheduled, not yet deleted
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)    # what conftest's flush does
    assert not Shiboken.isValid(first) and not Shiboken.isValid(second) and not Shiboken.isValid(nested)
    untracked = _Panel()                    # outside the block nothing is recorded
    assert Shiboken.isValid(untracked)
    untracked.deleteLater()


def test_deleting_leaves_a_widget_that_got_a_parent_to_its_parent():
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    with deleting(_Panel):
        child = _Panel()
        child.setParent(owner)
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert Shiboken.isValid(child)
    owner.deleteLater()
