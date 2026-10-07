"""Thin owned raw recording and portal stop controls for the Diagnostics Actions menu."""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Optional

from PySide6.QtCore import QTimer  # pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: native Qt binding
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.request_context import RequestBinding
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.wayland_input import WaylandInputSession


def _dispose(session: WaylandInputSession) -> None:
    """Close on a background thread without touching a destroyed widget."""
    try:
        session.close()
    except AutoControlException as failure:
        # The low-level owners retain their bounded cleanup for atexit/retry.
        autocontrol_logger.warning('Wayland panel cleanup failed: %s', failure)


class WaylandInputPanel(TranslatableMixin, QWidget):
    """Display raw physical results and actual stop binding; request only from Actions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self.session = WaylandInputSession()
        self.devices = QLineEdit('["/dev/input/event0"]')
        self.trigger = QLineEdit('F7')
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.status = QLabel()
        self._worker: Optional[WorkerHandle] = None
        root, form = QVBoxLayout(self), QFormLayout()
        for key, control in [('wl_physical_devices', self.devices), ('wl_stop_trigger', self.trigger)]:
            label = QLabel()
            self._tr(label, key)
            form.addRow(label, control)
        root.addLayout(form)
        root.addWidget(self.status)
        root.addWidget(self.results)
        hint = QLabel()
        hint.setWordWrap(True)
        self._tr(hint, 'wl_raw_hint')
        root.addWidget(hint)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._status)
        self._timer.start()
        session = self.session
        self.destroyed.connect(lambda _owner=None: threading.Thread(
            target=_dispose, args=(session,), name='autocontrol-wayland-panel-close', daemon=True).start())
        self._status()

    def menu_actions(self) -> list[Any]:
        """Return explicit opt-in operations for the window-level Actions menu."""
        return [('wl_start_physical', self._start_physical), ('wl_stop_physical', self._stop_physical),
                ('wl_start_shortcut', self._start_shortcut), ('wl_stop_shortcut', self._stop_shortcut),
                ('wl_input_status', self._status)]

    def _submit(self, function: Callable[[], Any]) -> None:
        if self._worker is not None:
            return
        binding = RequestBinding.capture()
        self._worker = start_worker(self, CallWorker(lambda: binding.run(function)),
                                    on_done=self._done, on_fail=self._failed, on_thread_done=self._released)

    def _start_physical(self) -> None:
        try:
            devices = json.loads(self.devices.text())
        except json.JSONDecodeError as failure:
            self._failed(str(failure))
            return
        session = self.session
        self._submit(lambda: session.start_physical(devices))

    def _stop_physical(self) -> None:
        self._submit(self.session.stop_physical)

    def _start_shortcut(self) -> None:
        trigger, session = self.trigger.text(), self.session
        self._submit(lambda: session.start_shortcut(trigger))

    def _stop_shortcut(self) -> None:
        self._submit(self.session.stop_shortcut)

    def _status(self) -> None:
        if self._worker is not None:
            return
        # status() briefly reads local fields; no native operation or request occurs.
        snapshot = self.session.status()
        self.status.setText(json.dumps(snapshot, ensure_ascii=False))

    def _done(self, result: Any) -> None:
        self.results.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        self._status()

    def _failed(self, message: str) -> None:
        self.results.setPlainText(message)

    def _released(self) -> None:
        self._worker = None
