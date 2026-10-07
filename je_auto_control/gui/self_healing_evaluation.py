"""Self-Healing fixed-frame reports and explicit candidate revision controls."""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from PIL import Image
from PySide6.QtGui import QPixmap  # pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: native Qt bindings
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.action_journal.events import JSONValue
from je_auto_control.utils.executor.request_context import RequestBinding
from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.self_healing.evaluation_api import (
    accept_template_candidate,
    compare_healing_versions,
    create_template_candidate,
    preview_template_candidate,
    revert_template_revision,
    validate_template_candidate,
)
from je_auto_control.utils.self_healing.evaluation_models import HealingEvaluationError
from je_auto_control.utils.self_healing.report_views import FAILURE_COLUMNS, METRIC_COLUMNS, comparison_rows


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


@dataclass(frozen=True)
class _Preview:
    report: Dict[str, JSONValue]
    thumbnails: List[bytes]


def prepare_preview(report: Dict[str, JSONValue]) -> _Preview:
    """Decode checked revision thumbnails in the worker before GUI delivery."""
    thumbnails = []
    for kind in ('base', 'candidate'):
        path = report.get(kind + '_path')
        if not isinstance(path, str):
            continue
        content = scoped_path(path, operation='read').read_bytes()
        if hashlib.sha256(content).hexdigest() != report.get(kind + '_hash'):
            raise HealingEvaluationError('revision preview changed before decoding')
        with Image.open(io.BytesIO(content)) as image:
            image.thumbnail((180, 120))
            stream = io.BytesIO()
            image.save(stream, format='PNG')
            thumbnails.append(stream.getvalue())
    return _Preview(report, thumbnails)


# pylint: disable-next=too-many-instance-attributes  # reason: thin form retains inputs and result widgets
class SelfHealingEvaluationPanel(TranslatableMixin, QWidget):
    """Inputs and previews only; the enclosing tab exposes all commands in Actions."""

    def __init__(self, template_path: Callable[[], str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._template_path = template_path
        self._worker: Optional[WorkerHandle] = None
        self.dataset, self.report_path = QLineEdit(), QLineEdit()
        self.store, self.revision, self.candidate = QLineEdit(), QLineEdit(), QLineEdit()
        self.versions = QPlainTextEdit('{"before":{"template_path":"button.png"}}')
        self.versions.setMaximumHeight(70)
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setMaximumHeight(180)
        self._thumbnails = (QLabel(), QLabel())
        self.metrics, self.failures = QTableWidget(), QTableWidget()
        for table, columns in ((self.metrics, METRIC_COLUMNS), (self.failures, FAILURE_COLUMNS)):
            table.setColumnCount(len(columns))
            table.setHorizontalHeaderLabels([_t('heal_metric_' + column) for column in columns])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setMaximumHeight(130)
        self._layout()

    def retranslate(self) -> None:
        """Refresh form labels and metric headers while retaining preview images."""
        super().retranslate()
        for table, columns in ((self.metrics, METRIC_COLUMNS), (self.failures, FAILURE_COLUMNS)):
            table.setHorizontalHeaderLabels([_t('heal_metric_' + column) for column in columns])

    def _layout(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()
        fields = [('heal_eval_dataset', self.dataset), ('heal_eval_versions', self.versions),
                  ('heal_eval_report_path', self.report_path), ('heal_eval_store', self.store),
                  ('heal_eval_revision', self.revision), ('heal_eval_candidate_path', self.candidate)]
        for key, widget in fields:
            form.addRow(self._tr(QLabel(), key), widget)
        root.addLayout(form)
        images = QHBoxLayout()
        for label, key in zip(self._thumbnails, ('heal_eval_base_preview', 'heal_eval_candidate_preview')):
            preview = QVBoxLayout()
            preview.addWidget(self._tr(QLabel(), key))
            preview.addWidget(label)
            images.addLayout(preview)
        root.addLayout(images)
        root.addWidget(self.metrics)
        root.addWidget(self.failures)
        root.addWidget(self.results)

    def menu_actions(self) -> list[Any]:
        """Comparison and review operations, with acceptance separate from preview."""
        return [('heal_eval_compare', self._compare), ('heal_eval_propose', self._propose),
                ('heal_eval_preview', self._preview), ('heal_eval_validate', self._validate),
                ('heal_eval_accept', self._accept), ('heal_eval_revert', self._revert)]

    def _compare(self) -> None:
        dataset = self.dataset.text().strip()
        if not dataset:
            dataset, _ = QFileDialog.getOpenFileName(self, _t('heal_eval_dataset'), '', 'JSON (*.json)')
            self.dataset.setText(dataset)
        if not dataset:
            return
        versions, output = self.versions.toPlainText(), self.report_path.text().strip() or None
        self._submit(lambda: compare_healing_versions(dataset, versions, report_path=output))

    def _propose(self) -> None:
        baseline = self._template_path().strip()
        candidate, store = self.candidate.text().strip(), self.store.text().strip()
        if not candidate:
            candidate, _ = QFileDialog.getOpenFileName(self, _t('heal_eval_candidate_path'), '', 'Images (*.png *.jpg)')
            self.candidate.setText(candidate)
        if candidate:
            self._submit(lambda: create_template_candidate(store, baseline, candidate))

    def _preview(self) -> None:
        store, revision = self.store.text().strip(), self.revision.text().strip()
        self._submit(lambda: preview_template_candidate(store, revision))

    def _validate(self) -> None:
        store, revision, dataset = self.store.text().strip(), self.revision.text().strip(), self.dataset.text().strip()
        self._submit(lambda: validate_template_candidate(store, revision, dataset))

    def _accept(self) -> None:
        store, revision = self.store.text().strip(), self.revision.text().strip()
        self._submit(lambda: accept_template_candidate(store, revision))

    def _revert(self) -> None:
        store, revision = self.store.text().strip(), self.revision.text().strip()
        self._submit(lambda: revert_template_revision(store, revision))

    def _submit(self, function: Callable[[], Dict[str, JSONValue]]) -> None:
        if self._worker is not None:
            return
        binding = RequestBinding.capture()
        worker = CallWorker(lambda: binding.run(lambda: prepare_preview(function())))
        self._worker = start_worker(self, worker, on_done=self._show_result,
                                    on_fail=self._failed, on_thread_done=self._finished)

    def _show_result(self, result: object) -> None:
        if not isinstance(result, _Preview):
            return
        self.results.setPlainText(json.dumps(result.report, ensure_ascii=False, allow_nan=False, indent=2))
        for table, rows in zip((self.metrics, self.failures), comparison_rows(result.report)):
            table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, value in enumerate(row):
                    table.setItem(index, column, QTableWidgetItem(value))
        identifier = result.report.get('revision_id')
        if isinstance(identifier, str):
            self.revision.setText(identifier)
        for label, content in zip(self._thumbnails, result.thumbnails):
            pixmap = QPixmap()
            pixmap.loadFromData(content)
            label.setPixmap(pixmap)

    def _failed(self, error: str) -> None:
        self.results.setPlainText(error)

    def _finished(self) -> None:
        self._worker = None
