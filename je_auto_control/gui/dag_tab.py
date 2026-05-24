"""DAG Runner tab: edit, validate, and execute cross-host DAGs."""
import json
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.dag import (
    DagDefinitionError, DagRunResult, parse_dag, run_dag,
)


_COLUMNS = ("id", "host", "status", "duration_ms", "error")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class _DagWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, definition: dict, max_parallel: int) -> None:
        super().__init__()
        self._definition = definition
        self._max_parallel = max_parallel

    def run(self) -> None:
        try:
            result = run_dag(self._definition,
                             max_parallel=self._max_parallel)
        except (DagDefinitionError, RuntimeError) as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.finished.emit(result)


class DagTab(TranslatableMixin, QWidget):
    """Load a DAG JSON, validate it, execute, browse per-node status."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._editor = QTextEdit()
        self._editor.setPlaceholderText('{"nodes": [{"id": "...", ...}]}')
        self._max_parallel = QSpinBox()
        self._max_parallel.setRange(1, 64)
        self._max_parallel.setValue(4)
        self._status_label = QLabel()
        self._table = QTableWidget(0, len(_COLUMNS))
        self._thread: Optional[QThread] = None
        self._worker: Optional[_DagWorker] = None
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        for label_key, slot in (
                ("dag_load_btn", self._on_load),
                ("dag_validate_btn", self._on_validate),
                ("dag_run_btn", self._on_run),
        ):
            btn = QPushButton()
            btn.setObjectName(label_key)
            btn.clicked.connect(slot)
            controls.addWidget(btn)
        controls.addWidget(QLabel(_t("dag_parallel_label")))
        controls.addWidget(self._max_parallel)
        controls.addStretch()
        root.addLayout(controls)
        root.addWidget(self._editor, stretch=2)
        root.addWidget(self._status_label)
        root.addWidget(self._table, stretch=3)
        self._apply_translations()

    def _apply_translations(self) -> None:
        for key in ("dag_load_btn", "dag_validate_btn", "dag_run_btn"):
            btn = self.findChild(QPushButton, key)
            if btn is not None:
                btn.setText(_t(key))
        self._table.setHorizontalHeaderLabels(
            [_t(f"dag_col_{name}") for name in _COLUMNS],
        )

    # --- actions ---------------------------------------------------

    def _on_load(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("dag_load_btn"), "", "JSON (*.json);;All (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                self._editor.setPlainText(fp.read())
        except OSError as error:
            self._status_label.setText(f"{_t('dag_error')}: {error}")

    def _on_validate(self) -> None:
        definition = self._parse_editor()
        if definition is None:
            return
        try:
            dag = parse_dag(definition)
            order = dag.topological_order()
        except DagDefinitionError as error:
            self._status_label.setText(f"{_t('dag_invalid')}: {error}")
            return
        self._status_label.setText(
            _t("dag_valid").replace("{count}", str(len(order))),
        )

    def _on_run(self) -> None:
        definition = self._parse_editor()
        if definition is None:
            return
        if self._thread is not None and self._thread.isRunning():
            self._status_label.setText(_t("dag_already_running"))
            return
        self._status_label.setText(_t("dag_running"))
        self._spawn_worker(definition)

    def _spawn_worker(self, definition: dict) -> None:
        thread = QThread(self)
        worker = _DagWorker(definition, int(self._max_parallel.value()))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_worker_finished)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _parse_editor(self) -> Optional[dict]:
        raw = self._editor.toPlainText().strip()
        if not raw:
            self._status_label.setText(_t("dag_empty"))
            return None
        try:
            return json.loads(raw)
        except ValueError as error:
            self._status_label.setText(f"{_t('dag_invalid')}: {error}")
            return None

    def _on_worker_finished(self, result: DagRunResult) -> None:
        self._thread = None
        self._worker = None
        key = "dag_success" if result.succeeded else "dag_failure"
        self._status_label.setText(
            _t(key).replace("{seconds}", f"{result.elapsed_s:.2f}"),
        )
        self._populate_table(result)

    def _on_worker_failed(self, message: str) -> None:
        self._thread = None
        self._worker = None
        self._status_label.setText(f"{_t('dag_error')}: {message}")

    def _populate_table(self, result: DagRunResult) -> None:
        nodes = list(result.nodes.values())
        self._table.setRowCount(len(nodes))
        for row, node in enumerate(nodes):
            values = (
                node.id, node.host, node.status,
                f"{node.duration_ms:.1f}", node.error or "",
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()


__all__ = ["DagTab"]
