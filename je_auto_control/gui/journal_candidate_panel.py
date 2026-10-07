"""Journal candidate source, provenance and diff preview with explicit import/export."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, cast

from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: native Qt bindings
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.action_journal.events import JSONValue, safe_payload
from je_auto_control.utils.codegen.candidate_artifacts import write_candidate_artifacts
from je_auto_control.utils.codegen.candidate_diff import candidate_action_diff
from je_auto_control.utils.codegen.candidate_models import CandidateScript
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
from je_auto_control.utils.executor.request_context import RequestBinding


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


@dataclass(frozen=True)
class _Preview:
    candidate: CandidateScript
    diff: str


# pylint: disable-next=too-many-instance-attributes  # reason: form retains inputs, callbacks and preview state
class JournalCandidatePanel(TranslatableMixin, QWidget):
    """Review only; import changes editable actions and export saves explicit artifacts."""

    def __init__(self, get_actions: Callable[[], object], set_actions: Callable[[List[List[JSONValue]]], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._get_actions, self._set_actions = get_actions, set_actions
        self._candidate: Optional[CandidateScript] = None
        self._worker: Optional[WorkerHandle] = None
        self.journal, self.run_id = QLineEdit(), QLineEdit()
        self.target, self.code_style = QComboBox(), QComboBox()
        self.target.addItems(['pytest', 'python', 'robot'])
        self.code_style.addItems(['actions', 'calls'])
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(190)
        self._layout()

    def _layout(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for key, widget in (('journal_candidate_path', self.journal), ('journal_candidate_run', self.run_id),
                            ('journal_candidate_target', self.target), ('journal_candidate_style', self.code_style)):
            form.addRow(self._tr(QLabel(), key), widget)
        layout.addLayout(form)
        layout.addWidget(self.preview)

    def menu_actions(self) -> list[Any]:
        """Expose preview, import and export as distinct window Actions commands."""
        return [('journal_candidate_preview', self._preview_candidate),
                ('journal_candidate_import', self._import_candidate),
                ('journal_candidate_export', self._export_candidate)]

    def _preview_candidate(self) -> None:
        if self._worker is not None:
            return
        self._candidate = None
        source, identifier = self.journal.text().strip(), self.run_id.text().strip()
        target, style = self.target.currentText(), self.code_style.currentText()
        current, _ = safe_payload(self._get_actions())

        def prepare() -> _Preview:
            candidate = generate_candidate_from_log(Path(source), run_id=identifier, target=target, style=style)
            return _Preview(candidate, candidate_action_diff(candidate, current))

        self._submit(prepare)

    def _import_candidate(self) -> None:
        if self._candidate is not None and self._worker is None:
            copied, _ = safe_payload(self._candidate.actions)
            if isinstance(copied, list):
                self._set_actions(cast(List[List[JSONValue]], copied))

    def _export_candidate(self) -> None:
        candidate = self._candidate
        if candidate is None or self._worker is not None:
            return
        path, _ = QFileDialog.getSaveFileName(self, _t('journal_candidate_export'), '', 'Source (*.py *.robot)')
        if path:
            self._submit(lambda: write_candidate_artifacts(candidate, path))

    def _submit(self, function: Callable[[], object]) -> None:
        if self._worker is not None:
            return
        binding = RequestBinding.capture()
        worker = CallWorker(lambda: binding.run(function))
        self._worker = start_worker(self, worker, on_done=self._show_result,
                                    on_fail=self._failed, on_thread_done=self._finished)

    def _show_result(self, result: object) -> None:
        if isinstance(result, _Preview):
            self._candidate = result.candidate
            sections = [*result.candidate.warnings, result.diff, result.candidate.code,
                        json.dumps(result.candidate.manifest, ensure_ascii=False, allow_nan=False, indent=2)]
            self.preview.setPlainText('\n\n'.join(sections))
        elif isinstance(result, dict):
            self.preview.appendPlainText(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))

    def _failed(self, error: str) -> None:
        self.preview.setPlainText(error)

    def _finished(self) -> None:
        self._worker = None
