"""Read-only lifecycle snapshots and provenance links inside Run History."""
from __future__ import annotations

import json
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.gui.journal_browser_worker import JournalReadOutcome, JournalReadRequest, JournalReadWorker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.history_store import JournalLink

_COLUMNS = ("sequence", "status", "command", "run_id", "step_id", "parent_id")


# pylint: disable-next=too-many-instance-attributes  # reason: the view owns its child controls and one reader
class JournalBrowser(TranslatableMixin, QWidget):
    """Inspect an explicit file or a selected history link without executing its contents."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._generation = 0
        self._handle: Optional[WorkerHandle] = None
        self._worker: Optional[JournalReadWorker] = None
        self._events: list[dict[str, object]] = []
        self._status_key, self._status_value = "journal_idle", ""
        self._path, self._run_id = QLineEdit(), QLineEdit()
        self._links = QComboBox()
        self._links.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._links.setMinimumContentsLength(16)
        # pylint: disable-next=no-member  # reason: PySide binds this Qt signal at runtime
        self._links.currentIndexChanged.connect(self._select_link)
        self._limit = QSpinBox()
        self._limit.setRange(1, 10000)
        self._limit.setValue(100)
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # pylint: disable-next=no-member  # reason: PySide binds this Qt signal at runtime
        self._table.itemSelectionChanged.connect(self._show_details)
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._build_layout()
        self.set_links([])
        self.retranslate()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._tr(QLabel(), "journal_heading"))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for key, control in (("journal_links", self._links), ("journal_path", self._path),
                             ("journal_run", self._run_id), ("journal_limit", self._limit)):
            form.addRow(self._tr(QLabel(), key), control)
        layout.addLayout(form)
        views = QSplitter(Qt.Orientation.Horizontal)
        views.addWidget(self._table)
        views.addWidget(self._details)
        views.setStretchFactor(0, 2)
        views.setStretchFactor(1, 1)
        layout.addWidget(views, stretch=1)
        layout.addWidget(self._status)

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Expose file selection, inspection and cancellation through the Actions menu."""
        return [("journal_browse", self.browse), ("journal_read", self.read), ("journal_cancel", self.cancel)]

    def retranslate(self) -> None:
        """Refresh labels without losing the selected snapshot or current read state."""
        TranslatableMixin.retranslate(self)
        self._table.setHorizontalHeaderLabels([
            language_wrapper.translate(f"journal_col_{column}") for column in _COLUMNS])
        if self._links.count():
            self._links.setItemText(0, language_wrapper.translate("journal_links_none"))
        self._set_status(self._status_key, self._status_value)

    def _set_status(self, key: str, value: str = "") -> None:
        self._status_key, self._status_value = key, value
        self._status.setText(language_wrapper.translate(key).replace("{value}", value))

    def _clear_events(self) -> None:
        self._events = []
        self._table.setRowCount(0)
        self._details.clear()

    def set_links(self, links: Sequence[JournalLink]) -> None:
        """Select provenance metadata without opening a file; discard any older read result."""
        self.cancel()
        self._generation += 1
        self._clear_events()
        self._links.blockSignals(True)
        self._links.clear()
        self._links.addItem(language_wrapper.translate("journal_links_none"), None)
        for link in links:
            self._links.addItem(f"{link.journal_run_id} — {link.journal_path}", link)
        self._links.setCurrentIndex(1 if links else 0)
        self._links.blockSignals(False)
        self._select_link(self._links.currentIndex())

    def _select_link(self, index: int) -> None:
        self.cancel()
        self._generation += 1
        self._clear_events()
        link = self._links.itemData(index)
        self._path.setText(link.journal_path if isinstance(link, JournalLink) else "")
        self._run_id.setText(link.journal_run_id if isinstance(link, JournalLink) else "")
        self._set_status("journal_idle")

    def browse(self) -> None:
        """Choose a source file without reading or rewriting it."""
        if self._handle is not None:
            return
        try:
            authorize_command("AC_journal_read")
        except AutoControlException as error:
            self._failed(str(error))
            return
        path, _ = QFileDialog.getOpenFileName(self, language_wrapper.translate("journal_browse"), "",
                                             "JSONL (*.jsonl);;All files (*)")
        if path:
            self.set_links([])
            self._path.setText(path)

    def read(self) -> None:
        """Launch bounded inspection; one active reader belongs to this widget."""
        if self._handle is not None:
            return
        self._clear_events()
        try:
            authorize_command("AC_journal_read")
        except AutoControlException as error:
            self._failed(str(error))
            return
        path = self._path.text()
        if not path.strip():
            self._set_status("journal_choose_path")
            return
        self._generation += 1
        request = JournalReadRequest(self._generation, path, self._run_id.text() or None, self._limit.value())
        worker = JournalReadWorker(request)
        self._worker = worker
        worker.progress.connect(self._progress)
        # pylint: disable-next=no-member  # reason: PySide binds this Qt signal at runtime
        self.destroyed.connect(worker.request_stop)
        self._set_busy(True)
        self._set_status("journal_reading")
        self._handle = start_worker(self, worker, on_done=self._received,
                                    on_thread_done=self._thread_done, on_fail=self._failed)

    def cancel(self) -> None:
        """Ask the current reader to stop at its next validated-record boundary."""
        if self._worker is not None:
            self._worker.request_stop()
            self._set_status("journal_cancelling")

    # pylint: disable-next=invalid-name  # reason: Qt override
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Request cancellation as soon as the view closes, before deferred deletion."""
        self.cancel()
        super().closeEvent(event)

    def report_error(self, message: str) -> None:
        """Display a failed provenance lookup without leaving old snapshots visible."""
        self._failed(message)

    def _set_busy(self, busy: bool) -> None:
        for control in (self._path, self._run_id, self._limit, self._links):
            control.setEnabled(not busy)

    @Slot(int, int)
    def _progress(self, request_id: int, count: int) -> None:
        if request_id == self._generation and self._status_key != "journal_cancelling":
            self._set_status("journal_progress", str(count))

    def _received(self, result: JournalReadOutcome) -> None:
        if result.request_id != self._generation:
            return
        if result.status == "cancelled":
            self._set_status("journal_cancelled")
        elif result.status == "error":
            self._failed(result.error)
        else:
            self._events = result.events
            self._table.setRowCount(len(result.events))
            for row, event in enumerate(result.events):
                for column, name in enumerate(_COLUMNS):
                    value = event.get(name)
                    self._table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))
            self._set_status("journal_done", str(len(result.events)))

    def _failed(self, message: str) -> None:
        self.cancel()
        self._generation += 1
        self._clear_events()
        self._set_status("journal_error", scrub_secret_text(message))

    def _thread_done(self) -> None:
        self._handle = self._worker = None
        self._set_busy(False)
        if self._status_key in ("journal_reading", "journal_progress", "journal_cancelling"):
            self._set_status("journal_interrupted")

    def _show_details(self) -> None:
        row = self._table.currentRow()
        self._details.setPlainText(json.dumps(self._events[row], ensure_ascii=False, indent=2)
                                   if 0 <= row < len(self._events) else "")
