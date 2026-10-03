"""Thin synchronization panel with explicit preview/exchange/apply and cancellable owned work."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, Optional

from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: native Qt bindings
    QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.config_sync import service
from je_auto_control.utils.config_sync.asset_service import config_sync_assets
from je_auto_control.utils.executor.request_context import RequestBinding


class _SyncWorker(CallWorker):
    def __init__(self, function: Callable[[], Dict[str, Any]], cancel: Event) -> None:
        super().__init__(function)
        self._cancel = cancel

    def request_stop(self) -> None:
        """Cooperatively stop between operations; the current bounded request may finish first."""
        self._cancel.set()


class ConfigSyncTab(TranslatableMixin, QWidget):  # pylint: disable=too-many-instance-attributes  # reason: public form controls and owned worker lifecycle
    """Show portable alternatives, committed revision, pending data and offline status."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self.definitions, self.workspace, self.server, self.user, self.secret = (QLineEdit() for _ in range(5))
        self.secret.setEchoMode(QLineEdit.Password)
        self.asset_manifest, self.asset_source = QLineEdit(), QLineEdit()
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.choices = QLineEdit('{}')
        self.status = QLabel()
        self._worker: Optional[WorkerHandle] = None
        self._cancel_event = Event()
        self._preview_result: Dict[str, Any] = {}
        root, form = QVBoxLayout(self), QFormLayout()
        for key, control in [('sync_definitions', self.definitions), ('sync_workspace', self.workspace),
                             ('sync_server', self.server), ('sync_user', self.user), ('sync_secret', self.secret),
                             ('sync_asset_manifest', self.asset_manifest), ('sync_asset_source', self.asset_source)]:
            label = QLabel()
            self._tr(label, key)
            form.addRow(label, control)
        root.addLayout(form)
        self._tr(self.choices, 'sync_choices')
        root.addWidget(self.choices)
        root.addWidget(self.status)
        root.addWidget(self.results)
        self._tr(self.status, 'sync_ready')
        stopped = self._cancel_event
        self.destroyed.connect(lambda _owner=None: stopped.set())

    def menu_actions(self) -> list:
        """Explicit operations exposed through the application's Actions menu."""
        return [('sync_preview', self._preview), ('sync_exchange', self._exchange),
                ('sync_apply', self._apply), ('sync_retry', self._retry), ('sync_status', self._status),
                ('sync_assets', self._assets), ('sync_cancel', self._cancel)]

    def _values(self) -> tuple[str, str, str, str, str]:
        return (self.definitions.text().strip(), self.workspace.text().strip(), self.server.text().strip(),
                self.user.text().strip(), self.secret.text())

    def _submit(self, function: Callable[[Event], Dict[str, Any]]) -> None:
        if self._worker is not None:
            return
        self._cancel_event.clear()
        cancel = self._cancel_event
        binding = RequestBinding.capture()
        worker = _SyncWorker(lambda: binding.run(lambda: function(cancel)), cancel)
        self._worker = start_worker(self, worker, on_done=self._done,
                                    on_thread_done=self._released, on_fail=self._failed)

    def _preview(self) -> None:
        values = self._values()
        self._submit(lambda cancel: service.config_sync_preview(*values, cancel=cancel))

    def _exchange(self) -> None:
        values = self._values()
        self._submit(lambda cancel: service.config_sync_exchange(*values, cancel=cancel))

    def _apply(self) -> None:
        preview = dict(self._preview_result)
        if not all(preview.get(key) for key in ('preview_path', 'state_path', 'device_id')):
            return
        definitions = self.definitions.text().strip()
        choices = self.choices.text()
        self._submit(lambda _cancel: service.config_sync_apply(
            definitions, preview['preview_path'], preview['state_path'], preview['device_id'], choices=choices))

    def _retry(self) -> None:
        _, workspace, server, user, secret = self._values()
        self._submit(lambda cancel: service.config_sync_retry(workspace, server, user, secret, cancel=cancel))

    def _status(self) -> None:
        _, workspace, server, user, _ = self._values()
        self._submit(lambda _cancel: service.config_sync_status(workspace, server, user))

    def _assets(self) -> None:
        manifest, source = self.asset_manifest.text().strip(), self.asset_source.text().strip()
        destination = str(Path(self.definitions.text().strip()).parent)
        self._submit(lambda cancel: config_sync_assets(manifest, source, destination, cancel=cancel))

    def _cancel(self) -> None:
        self._cancel_event.set()

    def _done(self, result: Dict[str, Any]) -> None:
        if result.get('preview_path'):
            self._preview_result = dict(result)
        self.results.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        template = language_wrapper.translate('sync_summary')
        self.status.setText(template.format(revision=result.get('revision', 0), pending=result.get('pending', 0),
                                            conflicts=result.get('conflicts', 0), offline=result.get('offline', False),
                                            protected=result.get('cas_supported', False)))

    def _released(self) -> None:
        self._worker = None

    def _failed(self, message: str) -> None:
        self.status.setText(message)

    def closeEvent(self, event: Any) -> None:  # pylint: disable=invalid-name  # reason: Qt virtual method
        """Cancel this panel's worker when closed; relay lifetime prevents later widget writes."""
        self._cancel()
        super().closeEvent(event)
