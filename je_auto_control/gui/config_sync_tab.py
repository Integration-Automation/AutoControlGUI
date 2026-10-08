"""Config Sync tab: this machine's sync state, and the commands that change it.

A thin view over :mod:`je_auto_control.utils.config_sync.session` -- every
command here is one call into it, so the same sync runs from a script
(``AC_config_sync_run``) or MCP with no GUI at all. The tab shows the last
merged revision, how many changes still wait in the outbox, whether the last
attempt reached the server, and the entries where two machines changed the
same thing and a person has to choose.

Syncing runs on a worker thread with a cancel event; closing the tab sets
the event, so a sync waiting on the network does not outlive its view.

Which sections a sync covers is chosen with one checkbox per section
(:data:`session.SYNCABLE_SECTIONS`). With every box ticked nothing is passed
and the session's default applies (hotkeys, triggers and the address book,
plus scripts / locators when their path is filled in); unticking one passes
the ticked ones as ``sections``. A ticked section whose path is empty is left
out, and the status lists the sections the last sync covered. Large scripts
travel through the shared folder, or -- with its box ticked -- through the
sync server itself (``assets_server``).

The server, user, the paths, the section choice and the ``assets_server``
switch are remembered between runs in the GUI settings file
(:mod:`je_auto_control.gui.window_settings`). The shared secret never is: that
file is plain text.
"""
import functools
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.window_settings import WindowSettings
from je_auto_control.utils.config_sync import session
from je_auto_control.utils.exception.exceptions import AutoControlException

_FIELDS = ("server", "user", "secret", "scripts", "locators", "assets")
#: What is kept between runs. Not "secret": the settings file is plain text.
_REMEMBERED = ("server", "user", "scripts", "locators", "assets")
#: The input that supplies each session option a section can need.
_OPTION_INPUT = {"scripts_dir": "scripts", "locators_path": "locators"}
_SECTIONS_KEY = "sections"
_ASSETS_SERVER_KEY = "assets_server"
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
        self._inputs["secret"].setEchoMode(QLineEdit.EchoMode.Password)
        self._sections: Dict[str, QCheckBox] = {
            name: QCheckBox() for name in session.SYNCABLE_SECTIONS}
        for box in self._sections.values():
            box.setChecked(True)
        self._assets_server = QCheckBox()
        self._note = ""
        self._restore_form()
        for name in _REMEMBERED:
            self._inputs[name].editingFinished.connect(self._remember_form)
        for box in (*self._sections.values(), self._assets_server):
            box.toggled.connect(self._on_choice_toggled)
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
        picker = QHBoxLayout()
        for name, box in self._sections.items():
            picker.addWidget(self._tr(box, f"config_sync_section_{name}"))
        picker.addStretch(1)
        form.addRow(self._tr(QLabel(), "config_sync_sections_label"), picker)
        form.addRow(self._tr(self._assets_server, "config_sync_assets_server_label"))
        root.addLayout(form)
        self._inputs["assets"].setEnabled(not self._assets_server.isChecked())
        root.addWidget(self._state)
        root.addWidget(self._detail)
        root.addWidget(self._tr(QLabel(), "config_sync_conflicts_title"))
        root.addWidget(self._conflicts, stretch=1)
        self._conflicts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._conflicts.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
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
            ("config_sync_collect_btn", self.collect_blobs),
        ]

    # --- inputs ------------------------------------------------------------

    def _restore_form(self) -> None:
        """Fill the remembered fields from the settings file; the secret is never among them."""
        saved = self._settings_store.load_form(_FORM_NAME)
        for name in _REMEMBERED:
            if saved.get(name):
                self._inputs[name].setText(saved[name])
        if _SECTIONS_KEY in saved:
            ticked = {name.strip() for name in saved[_SECTIONS_KEY].split(",")}
            for name, box in self._sections.items():
                box.setChecked(name in ticked)
        self._assets_server.setChecked(saved.get(_ASSETS_SERVER_KEY) == "1")

    def _remember_form(self) -> None:
        """Save the remembered fields as they stand (a field lost focus, or a sync is starting)."""
        fields = {name: self._inputs[name].text().strip() for name in _REMEMBERED}
        fields[_SECTIONS_KEY] = ",".join(
            name for name, box in self._sections.items() if box.isChecked())
        fields[_ASSETS_SERVER_KEY] = "1" if self._assets_server.isChecked() else "0"
        self._settings_store.save_form(_FORM_NAME, fields)

    def _on_choice_toggled(self, _checked: bool = False) -> None:
        """A section box or the assets switch changed: remember it, grey out what it replaces."""
        self._inputs["assets"].setEnabled(not self._assets_server.isChecked())
        self._remember_form()

    def _chosen_sections(self, values: Dict[str, str]) -> Optional[List[str]]:
        """The ``sections`` argument: ``None`` (the default) while every box is ticked.

        Otherwise the ticked sections, without those whose path is empty.
        """
        if all(box.isChecked() for box in self._sections.values()):
            return None
        chosen = []
        for name, box in self._sections.items():
            needs = session.SYNCABLE_SECTIONS[name]
            if box.isChecked() and (needs is None or values[_OPTION_INPUT[needs]]):
                chosen.append(name)
        return chosen

    def _settings(self, *, sections: bool = True) -> Optional[Dict[str, Any]]:
        """The form as session arguments, or ``None`` (with a message) if incomplete.

        ``sections`` false leaves the section choice out, for the commands
        that do not sync (reading the status, blob housekeeping).
        """
        values = {name: field.text().strip() for name, field in self._inputs.items()}
        if not values["server"] or not values["user"]:
            self._detail.setText(_t("config_sync_required"))
            return None
        options: Dict[str, Any] = {
            "secret": values["secret"], "scripts_dir": values["scripts"],
            "locators_path": values["locators"]}
        if self._assets_server.isChecked():
            options[_ASSETS_SERVER_KEY] = True
        else:
            options["assets_dir"] = values["assets"]
        chosen = self._chosen_sections(values) if sections else None
        if chosen is not None:
            if not chosen:
                self._detail.setText(_t("config_sync_no_sections"))
                return None
            options[_SECTIONS_KEY] = chosen
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
        return answer == QMessageBox.StandardButton.Yes

    def collect_blobs(self) -> None:
        """Delete this account's blobs on the server that no synced entry names any more."""
        settings = self._settings(sections=False)
        if settings is None or not self._confirm(_t("config_sync_collect_confirm")):
            return
        secret = settings["options"].get("secret")
        self._start(lambda: session.config_sync_collect_blobs(
            settings["server_url"], settings["user_id"], secret=secret),
            threading.Event(), on_done=self._on_collected)

    def _start(self, call: Callable[[], Dict[str, Any]], cancel: threading.Event,
               on_done: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        if self.is_busy():
            self._detail.setText(_t("config_sync_busy"))
            return
        self._cancel_slot[:] = [cancel]
        self._note = ""
        self._status = {**self._status, "state": "syncing", "error": ""}
        self._render()
        self._worker = start_worker(
            self, CallWorker(call), on_done=on_done or self._on_report,
            on_fail=self._on_failed, on_thread_done=self._on_thread_done)

    def cancel(self) -> None:
        """Ask the running sync to stop; its changes stay in the outbox."""
        _release(self._cancel_slot)

    def refresh_status(self) -> None:
        """Re-read the recorded state from the outbox; no network."""
        settings = self._settings(sections=False)
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
        section, key, choice = item.data(Qt.ItemDataRole.UserRole)
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

    def _on_collected(self, result: Dict[str, Any]) -> None:
        self._status = {**self._status, "state": "never"}
        self._note = _t("config_sync_collect_done").format(
            deleted=len(result.get("deleted") or ()), freed=int(result.get("freed") or 0),
            kept=int(result.get("kept") or 0), recent=len(result.get("recent") or ()))
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
        self._detail.setText("\n".join(self._detail_lines(status)))
        self._render_conflicts(status.get("conflict_details") or [])

    def _detail_lines(self, status: Dict[str, Any]) -> List[str]:
        """The lines under the state: revision, queue, last success, sections, error, note."""
        succeeded = float(status.get("last_success") or 0.0)
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(succeeded)) if succeeded else "-"
        lines = [
            f"{_t('config_sync_revision')}: {int(status.get('revision') or 0)}",
            f"{_t('config_sync_pending')}: {int(status.get('pending') or 0)}",
            f"{_t('config_sync_last_success')}: {when}",
        ]
        if status.get("sections"):
            covered = ", ".join(str(name) for name in status["sections"])
            lines.append(f"{_t('config_sync_sections_covered')}: {covered}")
        if status.get("error"):
            lines.append(f"{_t('config_sync_error')}: {status['error']}")
        if self._note:
            lines.append(self._note)
        return lines

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
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                item.setData(Qt.ItemDataRole.UserRole, (detail["section"], detail["key"], index))
                self._conflicts.setItem(row, column, item)


__all__ = ["ConfigSyncTab"]
