"""Thin synchronization panel with explicit preview/exchange/apply and cancellable owned work."""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, Optional

from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: native Qt bindings
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.task_controller import CancellationToken, TaskController, TaskError, TaskHandle, TaskResult
from je_auto_control.utils.config_sync import service
from je_auto_control.utils.config_sync.asset_service import config_sync_assets


def _sync_call(function: Callable[[Event], Dict[str, Any]], token: CancellationToken) -> object:
    token.checkpoint()
    return function(token.event)


class ConfigSyncTab(TranslatableMixin, QWidget):  # pylint: disable=too-many-instance-attributes  # reason: public form controls and owned worker lifecycle
    """Show portable alternatives, committed revision, pending data and offline status."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self.definitions, self.workspace, self.server, self.user, self.secret = (QLineEdit() for _ in range(5))
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.asset_manifest, self.asset_source = QLineEdit(), QLineEdit()
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.choices = QLineEdit('{}')
        self.status = QLabel()
        self._worker: Optional[TaskHandle] = None
        self._tasks = TaskController(timeout_s=300)
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

    def menu_actions(self) -> list[Any]:
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
        self._worker = self._tasks.submit(partial(_sync_call, function), owner=self)
        self._cancel_event = self._worker.token.event
        self._worker.completed.connect(self._task_done)
        self._worker.failed.connect(self._task_failed)
        self._worker.finished.connect(self._released)

    def _task_done(self, result: TaskResult) -> None:
        if isinstance(result.value, dict):
            self._done(result.value)

    def _task_failed(self, error: TaskError) -> None:
        self._failed(error.message)

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
        self._tasks.cancel_owner(self)

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
