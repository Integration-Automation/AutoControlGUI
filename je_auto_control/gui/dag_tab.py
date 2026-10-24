"""DAG Runner tab: edit, validate, and execute cross-host DAGs."""
import json
import threading
from contextvars import copy_context
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QSpinBox,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.dag import (
    DagDefinitionError, DagRunResult, parse_dag, run_dag,
)
from je_auto_control.utils.agent_runtime.api import inspect_agent_dag
from je_auto_control.utils.dag.managed_tasks import managed_stop_scope
from je_auto_control.utils.exception.exceptions import AutoControlException


_COLUMNS = ("id", "host", "status", "task_id", "duration_ms", "error")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class _DagWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, definition: dict, max_parallel: int,
                 stop_event: threading.Event, *, inspect_only: bool = False) -> None:
        super().__init__()
        self._definition = definition
        self._max_parallel = max_parallel
        self._stop_event = stop_event
        self._context = copy_context()
        self._inspect_only = inspect_only

    def request_stop(self) -> None:
        """Stop scheduling; managed nodes request owned pause, other running nodes finish."""
        self._stop_event.set()

    def run(self) -> None:
        try:
            result = self._context.run(self._execute)
        except (AutoControlException, RuntimeError) as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.finished.emit(result)

    def _execute(self) -> DagRunResult | dict:
        if self._inspect_only:
            with managed_stop_scope(self._stop_event):
                return inspect_agent_dag(self._definition)
        return run_dag(self._definition, max_parallel=self._max_parallel, stop_event=self._stop_event)


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
        self._thread: Optional[WorkerHandle] = None
        self._stop_event = threading.Event()
        self._inspection_source = ""
        self._inspection_output = QPlainTextEdit()
        self._inspection_output.setReadOnly(True)
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    def _build_layout(self) -> None:
        # Load/validate/run commands run from the Actions menu; the tab
        # keeps only the editor, the parallel input, table, and status.
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(_t("dag_parallel_label")))
        controls.addWidget(self._max_parallel)
        controls.addStretch()
        root.addLayout(controls)
        root.addWidget(self._editor, stretch=2)
        root.addWidget(self._status_label)
        root.addWidget(self._table, stretch=3)
        root.addWidget(self._inspection_output)
        self._apply_translations()

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("dag_load_btn", self._on_load),
            ("dag_validate_btn", self._on_validate),
            ("dag_inspect_btn", self._on_inspect),
            ("dag_run_btn", self._on_run),
            ("dag_stop_btn", self._on_stop),
        ]

    def _apply_translations(self) -> None:
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
        self._request_run(inspect_only=False)

    def _on_inspect(self) -> None:
        self._request_run(inspect_only=True)

    def _request_run(self, *, inspect_only: bool) -> None:
        definition = self._parse_editor()
        if definition is None:
            return
        if self._thread is not None and self._thread.isRunning():
            self._status_label.setText(_t("dag_already_running"))
            return
        self._status_label.setText(_t("dag_inspecting" if inspect_only else "dag_running"))
        self._spawn_worker(definition, inspect_only=inspect_only)

    def _spawn_worker(self, definition: dict, *, inspect_only: bool = False) -> None:
        self._stop_event = threading.Event()
        worker = _DagWorker(definition, int(self._max_parallel.value()),
                            self._stop_event, inspect_only=inspect_only)
        self._inspection_source = self._editor.toPlainText()
        self._inspection_output.clear()
        on_done = self._on_inspection_finished if inspect_only else self._on_worker_finished
        self._thread = start_worker(
            self, worker, on_done=on_done,
            on_fail=self._on_worker_failed, on_thread_done=self._on_thread_done)

    def _on_stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._status_label.setText(_t("dag_stopping"))

    def _on_thread_done(self) -> None:
        self._thread = None

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

    def _on_inspection_finished(self, result: dict) -> None:
        if self._inspection_source != self._editor.toPlainText():
            self._status_label.setText(_t("dag_inspection_stale"))
            return
        self._status_label.setText(_t("dag_inspection_note"))
        self._inspection_output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        rows = result.get("nodes", [])
        values = [(row.get("id", ""), row.get("host", ""), row.get("task_state", "unknown"),
                   row.get("task_id") or "", "", row.get("error", "")) for row in rows]
        self._render_rows(values)

    def _on_worker_finished(self, result: DagRunResult) -> None:
        key = "dag_success" if result.succeeded else "dag_failure"
        self._status_label.setText(
            _t(key).replace("{seconds}", f"{result.elapsed_s:.2f}"),
        )
        self._populate_table(result)

    def _on_worker_failed(self, message: str) -> None:
        self._status_label.setText(f"{_t('dag_error')}: {message}")

    def _populate_table(self, result: DagRunResult) -> None:
        nodes = list(result.nodes.values())
        rows = []
        for node in nodes:
            task_id = node.result.get("task_id", "") if isinstance(node.result, dict) else ""
            rows.append((
                node.id, node.host, node.status, task_id or "",
                f"{node.duration_ms:.1f}", node.error or "",
            ))
        self._render_rows(rows)

    def _render_rows(self, rows: list[tuple]) -> None:
        self._table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()


__all__ = ["DagTab"]
