"""Lazy Actions-menu workspace synchronization, causal review and explicit live preference application."""
from concurrent.futures import CancelledError
from functools import partial
import json
from typing import Callable, Optional, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.gui.config_sync_worker import ConfigSyncWorker, SyncUIOutcome, SyncUIRequest
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.config_sync.adapter_schema import KINDS
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.path_guard import PathPolicy

_OPERATIONS = ('status', 'capture', 'sync', 'register', 'ack', 'review', 'resolve', 'materialize',
               'preferences', 'retire', 'collect', 'full_resync')
_NETWORK = frozenset({'sync', 'register', 'ack', 'retire', 'collect', 'full_resync'})


def _t(key: str) -> str:
    return language_wrapper.translate('config_sync_' + key)


# pylint: disable-next=too-many-instance-attributes  # reason: owned form controls, review snapshot and one worker lifecycle
class ConfigSyncTab(TranslatableMixin, QWidget):
    """No connection, source capture, activation or credential lookup occurs when the tab is constructed."""

    def __init__(self, parent: Optional[QWidget] = None, *, path_policy: Optional[PathPolicy] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._policy = path_policy
        self._generation = 0
        self._worker: Optional[ConfigSyncWorker] = None
        self._handle: Optional[WorkerHandle] = None
        self._reviewed: Optional[dict[str, dict[str, object]]] = None
        self._row_ids: list[str] = []
        self._last_sync: object = None
        self._metrics: dict[str, object] = {}
        self._status_key = 'idle'
        self._status_detail = ''
        layout = self._build_form()
        self._build_review(layout)
        # pylint: disable-next=no-member  # reason: PySide6 bound signals expose connect at runtime
        self._configuration.textChanged.connect(self._invalidate)
        # pylint: disable-next=no-member  # reason: PySide6 bound signals expose connect at runtime
        self._kind.currentTextChanged.connect(self._invalidate_review)
        # pylint: disable-next=no-member  # reason: PySide6 bound signals expose connect at runtime
        self._heads.itemSelectionChanged.connect(self._select_head)
        self.retranslate()

    def _label(self, key: str) -> QLabel:
        label = QLabel(self)
        self._tr(label, 'config_sync_' + key)
        return label

    def _build_form(self) -> QVBoxLayout:
        layout = QVBoxLayout(self)
        note = self._label('notice')
        note.setWordWrap(True)
        layout.addWidget(note)
        self._form = QWidget(self)
        form = QFormLayout(self._form)
        self._configuration = QPlainTextEdit(self)
        self._configuration.setMaximumHeight(160)
        self._tr(self._configuration, 'config_sync_configuration_hint', 'setPlaceholderText')
        form.addRow(self._label('configuration'), self._configuration)
        self._secret_env = QLineEdit(self)
        form.addRow(self._label('secret_env'), self._secret_env)
        self._timeout = QDoubleSpinBox(self)
        self._timeout.setRange(0.1, 300)
        self._timeout.setValue(5)
        form.addRow(self._label('timeout'), self._timeout)
        self._peer = QLineEdit(self)
        form.addRow(self._label('peer'), self._peer)
        self._discard = QCheckBox(self)
        self._tr(self._discard, 'config_sync_discard')
        form.addRow(self._discard)
        self._target = QLineEdit(self)
        form.addRow(self._label('target'), self._target)
        self._kind = QComboBox(self)
        self._kind.addItems(sorted(KINDS))
        form.addRow(self._label('kind'), self._kind)
        layout.addWidget(self._form)
        return layout

    def _build_review(self, layout: QVBoxLayout) -> None:
        self._summary = QLabel(self)
        self._summary.setTextFormat(Qt.TextFormat.PlainText)
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)
        self._heads = QTableWidget(0, 6, self)
        self._heads.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._heads.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._heads.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._heads.setMinimumHeight(140)
        layout.addWidget(self._heads)
        self._value = QPlainTextEdit(self)
        self._value.setMaximumHeight(130)
        layout.addWidget(self._label('resolution_value'))
        layout.addWidget(self._value)
        self._deleted = QCheckBox(self)
        self._tr(self._deleted, 'config_sync_deleted')
        layout.addWidget(self._deleted)
        self._status = QLabel(self)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._details = QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._details.setMaximumHeight(150)
        layout.addWidget(self._details)

    def menu_actions(self) -> tuple[tuple[str, Callable[[], None]], ...]:
        """Expose explicit operations through the window's Actions menu."""
        return tuple(('config_sync_' + operation, partial(self.begin, operation)) for operation in _OPERATIONS) + (
            ('config_sync_cancel', self.cancel),)

    def retranslate(self) -> None:
        """Refresh labels without changing the private configuration or causal review."""
        super().retranslate()
        self._heads.setHorizontalHeaderLabels([_t(key) for key in (
            'entry', 'origin', 'change', 'version', 'deleted_column', 'value')])
        self._set_status(self._status_key, self._status_detail)
        self._show_metrics()

    def _invalidate(self) -> None:
        self._invalidate_review()
        self._metrics.clear()
        self._last_sync = None
        self._show_metrics()

    def _invalidate_review(self) -> None:
        self.cancel()
        self._generation += 1
        self._reviewed = None
        self._row_ids.clear()
        self._heads.setRowCount(0)
        self._value.clear()
        self._deleted.setChecked(False)
        self._details.clear()
        self._set_status('idle')

    def _options(self, operation: str) -> dict[str, object]:
        if operation in _NETWORK:
            return self._network_options(operation)
        if operation == 'review':
            return {'kind': self._kind.currentText()}
        if operation == 'materialize':
            return {'target_root': self._target.text().strip()}
        if operation == 'preferences':
            if self._kind.currentText() != 'workspace' or self._reviewed is None:
                raise ConfigSyncError(_t('review_preferences_first'))
            return {'observed': list(self._reviewed)}
        if operation == 'resolve':
            return self._resolution_options()
        return {}

    def _network_options(self, operation: str) -> dict[str, object]:
        options: dict[str, object] = {'timeout_s': self._timeout.value()}
        if self._secret_env.text().strip():
            options['secret_env'] = self._secret_env.text().strip()
        if operation == 'retire':
            options['peer_id'] = self._peer.text().strip()
        if operation == 'full_resync':
            options['discard_pending'] = self._discard.isChecked()
        return options

    def _resolution_options(self) -> dict[str, object]:
        row = self._heads.currentRow()
        if self._reviewed is None or not 0 <= row < len(self._row_ids):
            raise ConfigSyncError(_t('select_head_first'))
        entry = self._reviewed[self._row_ids[row]]
        if len(self._value.toPlainText().encode('utf-8')) > 1024 * 1024:
            raise ConfigSyncError(_t('value_too_large'))
        return {'kind': self._kind.currentText(), 'entry_id': entry['entry_id'],
                'observed': [key for key, head in self._reviewed.items() if head['entry_id'] == entry['entry_id']],
                'value': {} if self._deleted.isChecked() else json.loads(self._value.toPlainText()),
                'is_deleted': self._deleted.isChecked()}

    def begin(self, operation: str) -> None:
        """Snapshot one explicit menu operation and run it outside the GUI thread."""
        if self._handle is not None:
            self._set_status('busy')
            return
        try:
            options = self._options(operation)
            self._generation += 1
            request = SyncUIRequest(self._generation, operation, self._configuration.toPlainText(),
                                    json.dumps(options, allow_nan=False))
            self._worker = ConfigSyncWorker(request, path_policy=self._policy)
            self._form.setEnabled(False)
            self._heads.setEnabled(False)
            self._value.setEnabled(False)
            self._deleted.setEnabled(False)
            self._set_status('running')
            self._handle = start_worker(self, self._worker, on_done=self._received,
                                        on_thread_done=self._thread_done, on_fail=self._failed)
        except (AutoControlException, ValueError, TypeError, RuntimeError) as error:
            self._failed(scrub_secret_text(str(error)))

    def cancel(self) -> None:
        """Request cooperative stop; durable completed operations keep their result."""
        if self._worker is not None:
            self._worker.request_stop()
            self._set_status('cancelling')

    def _received(self, outcome: SyncUIOutcome) -> None:
        if outcome.request_id != self._generation or self._worker is None:
            return
        if outcome.status != 'ok':
            if outcome.status == 'error':
                self._failed(outcome.error)
            else:
                self._set_status('cancelled')
            return
        try:
            self._worker.deliver(partial(self._apply_result, outcome),
                                 require_active=outcome.operation == 'preferences')
        except CancelledError:
            self._set_status('cancelled')
        except (AutoControlException, ValueError, TypeError, RuntimeError) as error:
            self._failed(scrub_secret_text(str(error)))

    def _apply_result(self, outcome: SyncUIOutcome) -> None:
        data = outcome.data or {}
        self._details.setPlainText(json.dumps(data, ensure_ascii=False, indent=2)[:200000])
        if outcome.operation == 'review':
            self._show_heads(cast(dict[str, dict[str, object]], data['entries']))
        elif outcome.operation == 'preferences':
            apply = getattr(self.window(), 'apply_workspace_preferences', None)
            if not callable(apply):
                raise ConfigSyncError(_t('window_required'))
            apply(data)
        elif outcome.operation == 'resolve':
            self._reviewed = None
            self._row_ids.clear()
            self._heads.setRowCount(0)
        self._update_metrics(outcome.operation, data)
        self._set_status('applied' if outcome.operation == 'preferences' else 'done')

    def _update_metrics(self, operation: str, data: dict[str, object]) -> None:
        if operation not in {'status', 'sync'}:
            return
        self._metrics = dict(data)
        if operation == 'status':
            self._metrics['pending'] = (cast(int, cast(dict[str, object], data['outbox'])['pending'])
                + cast(int, cast(dict[str, object], data['control'])['pending']))
        if operation == 'sync' and data.get('state') == 'ready' and data.get('pending') == 0:
            self._last_sync = data.get('revision')
        self._show_metrics()

    def _show_heads(self, heads: dict[str, dict[str, object]]) -> None:
        self._reviewed = heads
        self._row_ids = sorted(heads)
        self._heads.setRowCount(len(heads))
        for row, key in enumerate(self._row_ids):
            entry = heads[key]
            values = (entry['entry_id'], entry['origin'], key, json.dumps(entry['version']),
                      entry['is_deleted'], json.dumps(entry['value'], ensure_ascii=False))
            for column, value in enumerate(values):
                self._heads.setItem(row, column, QTableWidgetItem(str(value)[:1000]))
        self._heads.resizeColumnsToContents()
        if heads:
            self._heads.selectRow(0)

    def _select_head(self) -> None:
        row = self._heads.currentRow()
        if self._reviewed is not None and 0 <= row < len(self._row_ids):
            entry = self._reviewed[self._row_ids[row]]
            self._value.setPlainText(json.dumps(entry['value'], ensure_ascii=False, indent=2))
            self._deleted.setChecked(entry['is_deleted'] is True)

    def _show_metrics(self) -> None:
        parts = [_t('last_sync') + ': ' + str(self._last_sync if self._last_sync is not None else '—')]
        for key in ('state', 'revision', 'pending', 'conflicts', 'unresolved'):
            if key in self._metrics:
                value = self._metrics[key]
                parts.append(_t(key) + ': ' + str(len(value) if isinstance(value, (list, tuple)) else value))
        self._summary.setText(' · '.join(parts))

    def _set_status(self, key: str, detail: str = '') -> None:
        self._status_key, self._status_detail = key, detail
        self._status.setText(_t(key) + (': ' + detail if detail else ''))

    def _failed(self, error: str) -> None:
        self._details.clear()
        self._set_status('error', scrub_secret_text(error))

    def _thread_done(self) -> None:
        self._handle = self._worker = None
        for control in (self._form, self._heads, self._value, self._deleted):
            control.setEnabled(True)
        if self._status_key in {'running', 'cancelling'}:
            self._set_status('interrupted')

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Invalidate queued results and request stop before destroying the panel."""
        self.cancel()
        self._generation += 1
        super().closeEvent(event)
