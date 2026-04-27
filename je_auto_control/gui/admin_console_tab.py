"""Admin console tab: manage many remote AutoControl REST endpoints."""
import json
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.admin.admin_client import (
    AdminConsoleClient, default_admin_console,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class _PollWorker(QObject):
    """Background poller — runs ``client.poll_all`` off the GUI thread."""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, client: AdminConsoleClient,
                 labels: Optional[List[str]] = None) -> None:
        super().__init__()
        self._client = client
        self._labels = labels

    def run(self) -> None:
        try:
            result = self._client.poll_all(labels=self._labels)
        except (OSError, RuntimeError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(result)


class AdminConsoleTab(TranslatableMixin, QWidget):
    """Thin Qt surface over :class:`AdminConsoleClient`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._client = default_admin_console()
        self._label_input = QLineEdit()
        self._url_input = QLineEdit()
        # Placeholder text only — the operator types the real URL.
        # Default scheme is http to match the bundled local server;
        # production deployments should put TLS in front via a reverse
        # proxy and the operator can paste an https://… URL here.
        self._url_input.setPlaceholderText("http://host:9939")  # NOSONAR python:S5332
        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.Password)
        self._table = QTableWidget(0, 5)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents,
        )
        self._actions_input = QTextEdit()
        self._actions_input.setPlaceholderText('[["AC_get_mouse_position"]]')
        self._broadcast_output = QTextEdit()
        self._broadcast_output.setReadOnly(True)
        self._poll_thread: Optional[QThread] = None
        self._build_layout()
        self._refresh_table()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._build_add_group())
        root.addWidget(self._table, stretch=1)
        root.addLayout(self._build_button_row())
        root.addWidget(self._build_broadcast_group(), stretch=1)

    def _build_add_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "admin_add_group")
        form = QHBoxLayout(group)
        form.addWidget(self._tr(QLabel(), "admin_label"))
        form.addWidget(self._label_input)
        form.addWidget(self._tr(QLabel(), "admin_url"))
        form.addWidget(self._url_input, stretch=1)
        form.addWidget(self._tr(QLabel(), "admin_token"))
        form.addWidget(self._token_input)
        add = self._tr(QPushButton(), "admin_add")
        add.clicked.connect(self._on_add)
        form.addWidget(add)
        return group

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for key, handler in (
            ("admin_remove", self._on_remove),
            ("admin_refresh", self._on_refresh),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _build_broadcast_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "admin_broadcast_group")
        form = QVBoxLayout(group)
        form.addWidget(self._tr(QLabel(), "admin_actions_label"))
        form.addWidget(self._actions_input)
        run = self._tr(QPushButton(), "admin_broadcast_run")
        run.clicked.connect(self._on_broadcast)
        form.addWidget(run)
        form.addWidget(self._tr(QLabel(), "admin_results_label"))
        form.addWidget(self._broadcast_output, stretch=1)
        return group

    def _on_add(self) -> None:
        label = self._label_input.text().strip()
        url = self._url_input.text().strip()
        token = self._token_input.text().strip()
        try:
            self._client.add_host(label=label, base_url=url, token=token)
        except ValueError as error:
            QMessageBox.warning(self, _t("admin_add"), str(error))
            return
        self._label_input.clear()
        self._url_input.clear()
        self._token_input.clear()
        self._refresh_table()

    def _on_remove(self) -> None:
        labels = self._selected_labels()
        if not labels:
            return
        for label in labels:
            self._client.remove_host(label)
        self._refresh_table()

    def _on_refresh(self) -> None:
        if self._poll_thread is not None:
            return
        thread = QThread(self)
        worker = _PollWorker(self._client)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._apply_poll_result)
        worker.failed.connect(self._apply_poll_failure)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_poll_thread_done)
        self._poll_thread = thread
        thread.start()

    def _on_broadcast(self) -> None:
        text = self._actions_input.toPlainText().strip()
        if not text:
            return
        try:
            actions = json.loads(text)
        except ValueError as error:
            QMessageBox.warning(self, _t("admin_broadcast_run"), str(error))
            return
        results = self._client.broadcast_execute(actions=actions)
        self._broadcast_output.setPlainText(
            json.dumps(results, indent=2, ensure_ascii=False, default=str),
        )

    def _apply_poll_result(self, statuses: list) -> None:
        self._refresh_table(statuses=statuses)

    def _apply_poll_failure(self, message: str) -> None:
        QMessageBox.warning(self, _t("admin_refresh"), message)

    def _on_poll_thread_done(self) -> None:
        self._poll_thread = None

    def _selected_labels(self) -> List[str]:
        rows = sorted({i.row() for i in self._table.selectedIndexes()})
        out: List[str] = []
        for row in rows:
            item = self._table.item(row, 0)
            if item is not None:
                out.append(item.text())
        return out

    def _refresh_table(self, statuses: Optional[list] = None) -> None:
        hosts = self._client.list_hosts()
        status_by_label = {s.label: s for s in (statuses or [])}
        self._table.setRowCount(len(hosts))
        self._table.setHorizontalHeaderLabels([
            _t("admin_col_label"), _t("admin_col_url"),
            _t("admin_col_health"), _t("admin_col_latency"),
            _t("admin_col_jobs"),
        ])
        for row, host in enumerate(hosts):
            self._table.setItem(row, 0, QTableWidgetItem(host.label))
            self._table.setItem(row, 1, QTableWidgetItem(host.base_url))
            status = status_by_label.get(host.label)
            if status is None:
                health_text = "?"
            elif status.healthy:
                health_text = _t("admin_health_ok")
            else:
                health_text = _t("admin_health_down")
            latency_text = "-" if status is None else f"{status.latency_ms:.0f} ms"
            jobs_text = "-" if status is None or status.job_count is None \
                else str(status.job_count)
            self._table.setItem(row, 2, QTableWidgetItem(health_text))
            self._table.setItem(row, 3, QTableWidgetItem(latency_text))
            self._table.setItem(row, 4, QTableWidgetItem(jobs_text))


__all__ = ["AdminConsoleTab"]
