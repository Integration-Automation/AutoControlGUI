"""The Script Builder's one-time reveal of the secrets a run produced.

``AC_user_add`` and ``AC_user_rotate_token`` answer with a bearer token that
exists nowhere else, and the builder masks it in its result pane. This dialog
is where the person who ran the step reads and copies it, once: each value is
in a read-only field labelled by its step -- the presentation the Users (RBAC)
group uses for a new token -- and closing the dialog empties the fields and
drops the values. Nothing here logs, saves or records a value; the only way
one leaves the dialog is the Copy button, onto the clipboard.

A value copied here stays on the clipboard after the dialog is gone, so once
one was copied the dialog offers a second way out, "Close and clear
clipboard". It empties the clipboard only while the clipboard still holds a
value copied from this dialog; anything put there since is left alone.

The tab opens it with ``open()`` (window-modal, not a nested event loop), only
when its "one-time values" button is pressed.
"""
from typing import List, Optional, Sequence

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.gui.script_builder.step_model import OneTimeValue

_PATH_SEPARATOR = " › "


def _t(key: str) -> str:
    return str(language_wrapper.translate(key, key))


def _copy_to_clipboard(text: str) -> None:
    """Put ``text`` on the clipboard; the one place a value leaves the dialog."""
    QGuiApplication.clipboard().setText(text)


def _clipboard_text() -> str:
    """What the clipboard holds now, as text."""
    return str(QGuiApplication.clipboard().text())


def _clear_clipboard() -> None:
    """Empty the clipboard."""
    QGuiApplication.clipboard().clear()


def _command_label(command: str) -> str:
    spec = COMMAND_SPECS.get(command)
    return spec.label if spec is not None else command


def path_label(value: OneTimeValue) -> str:
    """Where ``value``'s step ran: ``Step 2 › Loop run 3, step 1`` for a step inside a block."""
    if not value.path:
        return ""
    parts = [_t("sb_one_time_step").format(step=value.path[0].position)]
    for block, inner in zip(value.path, value.path[1:]):
        parts.append(_t("sb_one_time_inside").format(
            block=_command_label(block.command), run=inner.run, step=inner.position))
    return _PATH_SEPARATOR.join(parts)


def value_label(value: OneTimeValue) -> str:
    """What names ``value`` in the dialog: where its step ran, its command and whom it is for."""
    parts = [path_label(value), _command_label(value.command), value.subject, value.name]
    return " · ".join(part for part in parts if part)


class OneTimeValueDialog(QDialog):
    """Shows each value of a run once; forgets them all when it closes."""

    def __init__(self, values: Sequence[OneTimeValue],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("sb_one_time_title"))
        self._values: List[OneTimeValue] = list(values)
        self._fields: List[QLineEdit] = []
        self._copied: List[str] = []
        root = QVBoxLayout(self)
        notice = QLabel(_t("sb_one_time_notice"))
        notice.setWordWrap(True)
        root.addWidget(notice)
        grid = QGridLayout()
        for row, value in enumerate(self._values):
            self._add_row(grid, row, value)
        root.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self._clear_btn = buttons.addButton(_t("sb_one_time_close_clear"),
                                            QDialogButtonBox.ButtonRole.ActionRole)
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self.close_and_clear)
        root.addWidget(buttons)
        self.setMinimumWidth(560)
        self.finished.connect(self.forget)

    def _add_row(self, grid: QGridLayout, row: int, value: OneTimeValue) -> None:
        field = QLineEdit(value.value)
        field.setReadOnly(True)
        copy = QPushButton(_t("sb_one_time_copy"))
        copy.clicked.connect(lambda _checked=False, index=row: self.copy_value(index))
        grid.addWidget(QLabel(value_label(value)), row, 0)
        grid.addWidget(field, row, 1)
        grid.addWidget(copy, row, 2)
        self._fields.append(field)

    def labels(self) -> List[str]:
        """The label of each value still held, in the order shown."""
        return [value_label(value) for value in self._values]

    def shown_values(self) -> List[str]:
        """The text of each value field, in the order shown."""
        return [field.text() for field in self._fields]

    def copy_value(self, index: int) -> bool:
        """Copy value ``index`` to the clipboard; ``False`` once it is forgotten."""
        if not 0 <= index < len(self._values):
            return False
        text = self._values[index].value
        _copy_to_clipboard(text)
        self._copied.append(text)
        self._clear_btn.setEnabled(True)
        return True

    def can_clear_clipboard(self) -> bool:
        """Whether a value was copied from this dialog, so clearing is on offer."""
        return self._clear_btn.isEnabled()

    def clear_clipboard(self) -> bool:
        """Empty the clipboard if it still holds a value copied here; say whether it did."""
        copied, self._copied = self._copied, []
        self._clear_btn.setEnabled(False)
        if not copied or _clipboard_text() not in copied:
            return False
        _clear_clipboard()
        return True

    def close_and_clear(self) -> None:
        """The "Close and clear clipboard" button: clear what was copied here, then close."""
        self.clear_clipboard()
        self.reject()

    def forget(self, _result: int = 0) -> None:
        """Empty every field and drop the values; runs when the dialog closes."""
        for field in self._fields:
            field.setText("")  # also resets the field's undo history
        self._values = []
        self._copied = []
        self._clear_btn.setEnabled(False)


__all__ = ["OneTimeValueDialog", "path_label", "value_label"]
