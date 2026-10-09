"""The typed accessors the tabs use in place of a cast at every call site (offscreen Qt)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel, QPushButton, QTableWidget, QTableWidgetItem  # noqa: E402

from je_auto_control.gui._i18n_helpers import TranslatableMixin  # noqa: E402
from je_auto_control.gui._qt_typed import as_widget, filled_item  # noqa: E402
from je_auto_control.utils.exception.exceptions import AutoControlException  # noqa: E402


@pytest.fixture(autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_as_widget_is_the_object_itself():
    label = QLabel("x")
    assert as_widget(label) is label
    label.deleteLater()


def test_a_filled_cell_is_returned_and_a_missing_one_is_a_typed_error():
    table = QTableWidget(1, 2)
    item = QTableWidgetItem("job-1")
    table.setItem(0, 0, item)
    assert filled_item(table, 0, 0) is item and filled_item(table, 0, 0).text() == "job-1"
    with pytest.raises(AutoControlException, match="row 0, column 1"):
        filled_item(table, 0, 1)
    table.deleteLater()


def test_tr_hands_back_the_widget_it_was_given():
    """``_tr`` is generic over the widget class; at run time it has always returned its argument."""

    class _Tab(TranslatableMixin):
        """A translatable holder."""

    tab = _Tab()
    button = QPushButton()
    assert tab._tr(button, "audit_run") is button and button.text() != ""
    button.deleteLater()


def test_the_scoped_enum_spellings_are_the_members_the_short_ones_named():
    assert QAbstractItemView.EditTrigger.NoEditTriggers is QAbstractItemView.NoEditTriggers
    assert Qt.ItemFlag.ItemIsEditable is Qt.ItemIsEditable
    assert Qt.ItemDataRole.UserRole is Qt.UserRole
