"""Render an inert capability snapshot; rendering and language changes never invoke a provider."""
from typing import Optional

from PySide6.QtWidgets import QGroupBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.wrapper.capabilities import CapabilitySnapshot, CapabilityStatus


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class CapabilityView(QGroupBox):
    """Display separate input/capture state, backend, scope and recovery without retaining native objects."""

    def __init__(self) -> None:
        super().__init__()
        self._snapshot: Optional[CapabilitySnapshot] = None
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._table = QTableWidget(0, 4)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._table)
        self.retranslate()

    def set_snapshot(self, snapshot: CapabilitySnapshot) -> None:
        """Display metadata already obtained by the owner's explicit passive action."""
        self._snapshot = snapshot
        self.retranslate()

    def retranslate(self) -> None:
        """Translate and render only the cached metadata; never inspect the environment or native state."""
        self.setTitle(_t('diag_cap_title'))
        self._table.setHorizontalHeaderLabels([
            _t('diag_cap_name'), _t('diag_cap_backend'), _t('diag_cap_state'), _t('diag_col_detail'),
        ])
        if self._snapshot is None:
            self._summary.setText(_t('diag_cap_idle'))
            return
        self._summary.setText(_t('diag_cap_snapshot').format(
            platform=self._snapshot.platform, display=self._snapshot.display_server))
        self._table.setRowCount(2)
        for row, status in enumerate((self._snapshot.input, self._snapshot.capture)):
            self._set_status(row, status)
        self._table.resizeRowsToContents()

    def _set_status(self, row: int, status: CapabilityStatus) -> None:
        scope = _t('diag_cap_scope_desktop' if status.desktop_wide else 'diag_cap_scope_limited')
        details = f'{scope}: {status.reason}\n{status.recovery}'
        values = [_t('diag_cap_'+status.name), status.backend, _t('diag_cap_state_'+status.state), details]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            self._table.setItem(row, column, item)
