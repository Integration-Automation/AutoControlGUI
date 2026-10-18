"""Opted-in history and journal controls shared by manual execution surfaces."""
from __future__ import annotations

from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from typing import Iterator, Optional

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.utils.action_journal import ActionJournal, journal_scope
from je_auto_control.utils.logging.secret_scope import secret_log_scope
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.manual import manual_history_scope


class ManualRunControls(TranslatableMixin, QWidget):
    """Inputs only; unchecked history and an empty path preserve existing execution."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self.record_history = QCheckBox()
        self.journal_path = QLineEdit()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tr(self.record_history, "manual_history_record"))
        fields = QFormLayout()
        fields.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fields.addRow(self._tr(QLabel(), "manual_journal_optional"), self.journal_path)
        layout.addLayout(fields)

    @contextmanager
    def capture(self, *, source_id: str, script_path: str) -> Iterator[None]:
        """Bind requested ownership/capture around the caller's existing execution."""
        record, path = self.record_history.isChecked(), self.journal_path.text()
        if not record and not path:
            yield
            return
        with secret_log_scope(), ExitStack() as stack:
            authorize_command("AC_history_capture")
            candidate = validate_path(path) if path else None
            if record:
                stack.enter_context(manual_history_scope(source_id=source_id, script_path=script_path))
            if candidate is not None:
                stack.enter_context(journal_scope(ActionJournal(candidate)))
            yield


def _capture_manual_run(controls: Optional[ManualRunControls], *, source_id: str,
                        script_path: str) -> AbstractContextManager[object]:
    """Leave legacy embedder/stub hosts without the optional controls unchanged."""
    return controls.capture(source_id=source_id, script_path=script_path) if controls is not None else nullcontext()
