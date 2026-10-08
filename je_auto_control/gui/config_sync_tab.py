"""Config Sync tab: this machine's sync state, and the commands that change it.

A thin view over :mod:`je_auto_control.utils.config_sync.session` -- every
command here is one call into it, so the same sync runs from a script
(``AC_config_sync_run``) or MCP with no GUI at all. The tab shows the last
merged revision, how many changes still wait in the outbox, whether the last
attempt reached the server, and the entries where two machines changed the
same thing and a person has to choose.

Syncing runs on a worker thread with a cancel event; closing the tab sets
the event, so a sync waiting on the network does not outlive its view.

The server, user and the two folders are remembered between runs in the GUI
settings file (:mod:`je_auto_control.gui.window_settings`). The shared secret
never is: that file is plain text.
"""
import functools
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.window_settings import WindowSettings
from je_auto_control.utils.config_sync import session
from je_auto_control.utils.exception.exceptions import AutoControlException

_FIELDS = ("server", "user", "secret", "scripts", "assets")
#: What is kept between runs. Not "secret": the settings file is plain text.
_REMEMBERED = ("server", "user", "scripts", "assets")
_FORM_NAME = "config_sync"
_COLUMNS = ("entry", "choice", "origin", "value")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _release(events: List[threading.Event]) -> None:
    """Set every cancel event in ``events``."""
    for event in events:
        event.set()


class ConfigSyncTab(TranslatableMixin, QWidget):
    """Status and commands for cross-machine config sync."""

    def __init__(self, parent: Optional[QWidget] = None,
                 settings: Optional[WindowSettings] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._settings_store = settings if settings is not None else WindowSettings()
        self._inputs: Dict[str, QLineEdit] = {name: QLineEdit() for name in _FIELDS}
        self._inputs["secret"].setEchoMode(QLineEdit.Password)
        self._restore_form()
        for name in _REMEMBERED:
            self._inputs[name].editingFinished.connect(self._remember_form)
        self._state = QLabel()
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._conflicts = QTableWidget(0, len(_COLUMNS))
        self._status: Dict[str, Any] = {"state": "never"}
        self._worker: Optional[WorkerHandle] = None
        # Shared with the destroyed-signal handler, which must not touch self.
        self._cancel_slot: List[threading.Event] = []
        slot = self._cancel_slot
        self.destroyed.connect(lambda *_args: _release(slot))
        self._build_layout()
        self._render()

    # --- layout ------------------------------------------------------------

    def _build_layout(self) -> None:
        # Sync / cancel / refresh / resolve / full resync run from the Actions
        # menu; the tab keeps the inputs, the status lines and the conflicts.
        root = QVBoxLayout(self)
        form = QFormLayout()
        for name in _FIELDS:
            form.addRow(self._tr(QLabel(), f"config_sync_{name}_label"), self._inputs[name])
        root.addLayout(form)
        root.addWidget(self._state)
        root.addWidget(self._detail)
        root.addWidget(self._tr(QLabel(), "config_sync_conflicts_title"))
        root.addWidget(self._conflicts, stretch=1)
        self._conflicts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._conflicts.setSelectionBehavior(QTableWidget.SelectRows)
        self._apply_translations()

    def _apply_translations(self) -> None:
        self._conflicts.setHorizontalHeaderLabels(
            [_t(f"config_sync_col_{column}") for column in _COLUMNS])

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the sync still out, by setting its cancel event.

        Called by ``close_tab(key, release=True)`` before the widget is deleted; safe to call twice.
        """
        release_resources(self, functools.partial(_release, self._cancel_slot))

    def retranslate(self) -> None:
        """Re-apply the translated texts after a language change."""
        TranslatableMixin.retranslate(self)
        self._apply_translations()
        self._render()

    def menu_actions(self) -> List[Tuple[str, Callable[[], None]]]:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("config_sync_run_btn", self.sync_now),
            ("config_sync_cancel_btn", self.cancel),
            ("config_sync_refresh_btn", self.refresh_status),
            ("config_sync_resolve_btn", self.resolve_selected),
            ("config_sync_resync_btn", self.full_resync),
        ]

    # --- inputs ------------------------------------------------------------

    def _restore_form(self) -> None:
        """Fill the remembered fields from the settings file; the secret is never among them."""
        saved = self._settings_store.load_form(_FORM_NAME)
        for name in _REMEMBERED:
            if saved.get(name):
                self._inputs[name].setText(saved[name])

    def _remember_form(self) -> None:
        """Save the remembered fields as they stand (a field lost focus, or a sync is starting)."""
        self._settings_store.save_form(
            _FORM_NAME, {name: self._inputs[name].text().strip() for name in _REMEMBERED})

    def _settings(self) -> Optional[Dict[str, Any]]:
        """The form as session arguments, or ``None`` (with a message) if incomplete."""
        values = {name: field.text().strip() for name, field in self._inputs.items()}
        if not values["server"] or not values["user"]:
            self._detail.setText(_t("config_sync_required"))
            return None
        options = {"secret": values["secret"], "scripts_dir": values["scripts"],
                   "assets_dir": values["assets"]}
        return {"server_url": values["server"], "user_id": values["user"],
                "options": {name: value for name, value in options.items() if value}}

    def is_busy(self) -> bool:
        """Whether a sync is running."""
        return self._worker is not None and self._worker.isRunning()

    # --- commands ----------------------------------------------------------

    def sync_now(self) -> None:
        """Start one sync on a worker thread."""
        settings = self._settings()
        if settings is None:
            return
        self._remember_form()
        cancel = threading.Event()
        self._start(lambda: session.config_sync_run(
            settings["server_url"], settings["user_id"], cancel=cancel, force=True,
            **settings["options"]), cancel)

    def full_resync(self) -> None:
        """Adopt the server's state, discarding this machine's pending changes."""
        settings = self._settings()
        if settings is None or not self._confirm(_t("config_sync_resync_confirm")):
            return
        self._start(lambda: session.config_sync_full_resync(
            settings["server_url"], settings["user_id"], **settings["options"]),
            threading.Event())

    def _confirm(self, question: str) -> bool:
        answer = QMessageBox.question(self, _t("tab_config_sync"), question)
        return answer == QMessageBox.Yes

    def _start(self, call: Callable[[], Dict[str, Any]], cancel: threading.Event) -> None:
        if self.is_busy():
            self._detail.setText(_t("config_sync_busy"))
            return
        self._cancel_slot[:] = [cancel]
        self._status = {**self._status, "state": "syncing", "error": ""}
        self._render()
        self._worker = start_worker(
            self, CallWorker(call), on_done=self._on_report, on_fail=self._on_failed,
            on_thread_done=self._on_thread_done)

    def cancel(self) -> None:
        """Ask the running sync to stop; its changes stay in the outbox."""
        _release(self._cancel_slot)

    def refresh_status(self) -> None:
        """Re-read the recorded state from the outbox; no network."""
        settings = self._settings()
        if settings is None:
            return
        try:
            self._status = session.config_sync_status(settings["server_url"], settings["user_id"])
        except AutoControlException as error:
            self._status = {**self._status, "error": str(error)}
        self._render()

    def resolve_selected(self) -> None:
        """Keep the selected candidate of a conflict; the next sync sends the choice."""
        settings = self._settings()
        row = self._conflicts.currentRow()
        item = self._conflicts.item(row, 0) if row >= 0 else None
        if settings is None:
            return
        if item is None:
            self._detail.setText(_t("config_sync_no_conflict_selected"))
            return
        section, key, choice = item.data(Qt.UserRole)
        try:
            session.config_sync_resolve(settings["server_url"], settings["user_id"],
                                        section, key, choice, **settings["options"])
        except AutoControlException as error:
            self._detail.setText(f"{_t('config_sync_error')}: {error}")
            return
        self.refresh_status()

    # --- worker results ----------------------------------------------------

    def _on_report(self, report: Dict[str, Any]) -> None:
        self._status = dict(report)
        self.refresh_status()

    def _on_failed(self, message: str) -> None:
        self._status = {**self._status, "state": "offline", "error": message}
        self._render()

    def _on_thread_done(self) -> None:
        self._worker = None
        self._cancel_slot[:] = []

    # --- rendering ---------------------------------------------------------

    def _render(self) -> None:
        status = self._status
        state = str(status.get("state", "never"))
        text = f"{_t('config_sync_state_label')}: {_t(f'config_sync_state_{state}')}"
        retry_in = float(status.get("retry_in_s") or 0.0)
        if retry_in > 0 and state in ("backing_off", "offline"):
            text += f" ({_t('config_sync_retry_in').format(seconds=math.ceil(retry_in))})"
        self._state.setText(text)
        succeeded = float(status.get("last_success") or 0.0)
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(succeeded)) if succeeded else "-"
        lines = [
            f"{_t('config_sync_revision')}: {int(status.get('revision') or 0)}",
            f"{_t('config_sync_pending')}: {int(status.get('pending') or 0)}",
            f"{_t('config_sync_last_success')}: {when}",
        ]
        if status.get("error"):
            lines.append(f"{_t('config_sync_error')}: {status['error']}")
        self._detail.setText("\n".join(lines))
        self._render_conflicts(status.get("conflict_details") or [])

    def _render_conflicts(self, details: List[Dict[str, Any]]) -> None:
        rows = [(detail, index, choice) for detail in details
                for index, choice in enumerate(detail.get("choices", []))]
        self._conflicts.setRowCount(len(rows))
        for row, (detail, index, choice) in enumerate(rows):
            value = _t("config_sync_deleted") if choice.get("deleted") else str(choice.get("value"))
            cells = (f"{detail['section']}/{detail['key']}", str(index),
                     str(choice.get("origin", "")), value)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setData(Qt.UserRole, (detail["section"], detail["key"], index))
                self._conflicts.setItem(row, column, item)


__all__ = ["ConfigSyncTab"]
