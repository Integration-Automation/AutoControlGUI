"""GUI test: recording editor Undo (Ctrl+Z) restores after edits."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui.recording_editor_tab import (  # noqa: E402
    RecordingEditorTab,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _names(tab):
    return [action[0] for action in tab._actions]


def test_remove_then_undo_restores(qapp):
    tab = RecordingEditorTab()
    tab._actions = [["AC_a"], ["AC_b"], ["AC_c"]]
    tab._refresh()
    tab._list.setCurrentRow(1)
    tab._remove_selected()
    assert _names(tab) == ["AC_a", "AC_c"]
    tab._undo()
    assert _names(tab) == ["AC_a", "AC_b", "AC_c"]


def test_undo_with_empty_stack_is_a_noop(qapp):
    tab = RecordingEditorTab()
    tab._actions = [["AC_x"]]
    tab._refresh()
    tab._undo()  # nothing recorded yet
    assert _names(tab) == ["AC_x"]


def test_undo_unwinds_multiple_edits(qapp):
    tab = RecordingEditorTab()
    tab._actions = [["AC_a"], ["AC_b"]]
    tab._refresh()
    tab._list.setCurrentRow(0)
    tab._remove_selected()                  # -> [AC_b]
    tab._mutate([["AC_b"], ["AC_c"]])       # -> [AC_b, AC_c]
    assert _names(tab) == ["AC_b", "AC_c"]
    tab._undo()                             # back to [AC_b]
    assert _names(tab) == ["AC_b"]
    tab._undo()                             # back to [AC_a, AC_b]
    assert _names(tab) == ["AC_a", "AC_b"]
