"""Actions-driven candidate source, diff and provenance review with explicit editor transfer."""
from typing import Callable, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.gui.journal_candidate_worker import (
    CandidateOperation, JournalCandidateOutcome, JournalCandidateTask, JournalCandidateWorker,
)
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError, CandidateScript
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.rbac.policy import authorize_command


def _t(key: str) -> str:
    return language_wrapper.translate("journal_candidate_" + key)


# pylint: disable-next=too-many-instance-attributes  # reason: form and presentation controls plus one owned task
class JournalCandidatePanel(TranslatableMixin, QWidget):
    """Review a journal candidate before choosing a separate import or archive export."""

    def __init__(self, parent: Optional[QWidget] = None, *, baseline: str = "[]",
                    on_import: Optional[Callable[[CandidateScript], None]] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._baseline, self._on_import = baseline, on_import
        self._candidate: Optional[CandidateScript] = None
        self._generation = 0
        self._operation: CandidateOperation = "generate"
        self._handle: Optional[WorkerHandle] = None
        self._worker: Optional[JournalCandidateWorker] = None
        self._path, self._run_id = QLineEdit(), QLineEdit()
        self._target, self._style = QComboBox(), QComboBox()
        self._target.addItems(["pytest", "python", "robot"])
        self._style.addItems(["actions", "calls"])
        self._code, self._diff, self._manifest, self._warnings = (QPlainTextEdit() for _ in range(4))
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._status_key, self._status_value = "idle", ""
        self._build_layout()
        for control in (self._path, self._run_id):
            # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
            control.textChanged.connect(self._inputs_changed)
        for selector in (self._target, self._style):
            # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
            selector.currentTextChanged.connect(self._inputs_changed)
        self.retranslate()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        explanation = QLabel()
        self._tr(explanation, "journal_candidate_explanation")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        for key, control in (("path", self._path), ("run_id", self._run_id),
                             ("target", self._target), ("style", self._style)):
            form.addRow(self._tr(QLabel(), "journal_candidate_" + key), control)
        layout.addLayout(form)
        self._tabs = QTabWidget()
        for key, view in (("code", self._code), ("diff", self._diff),
                           ("manifest", self._manifest), ("warnings", self._warnings)):
            view.setReadOnly(True)
            index = self._tabs.addTab(view, "")
            self._tr_tab(self._tabs, index, "journal_candidate_" + key)
        layout.addWidget(self._tabs, stretch=1)
        layout.addWidget(self._status)

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Keep candidate operations in Actions; transfer is offered only with an explicit target editor."""
        actions = [("journal_candidate_browse", self._browse), ("journal_candidate_generate", self._start_generate),
                   ("journal_candidate_export", self._export), ("journal_candidate_cancel", self.cancel)]
        if self._on_import is not None:
            actions.insert(2, ("journal_candidate_import", self._import_candidate))
        return actions

    def retranslate(self) -> None:
        """Translate presentation without changing the source or reviewed candidate."""
        TranslatableMixin.retranslate(self)
        self._set_status(self._status_key, self._status_value)

    def _set_status(self, key: str, value: str = "") -> None:
        self._status_key, self._status_value = key, value
        self._status.setText(_t(key).replace("{value}", value))

    def _inputs_changed(self, *_args: object) -> None:
        self.cancel()
        self._generation += 1
        self._candidate = None
        for view in (self._code, self._diff, self._manifest, self._warnings):
            view.clear()
        self._set_status("idle")

    def _browse(self) -> None:
        if self._handle is not None:
            return
        try:
            authorize_command("AC_generate_candidate_from_log")
            path, _ = QFileDialog.getOpenFileName(self, _t("browse"), self._path.text(), "JSONL (*.jsonl);;All (*)")
            if path:
                self._path.setText(path)
        except AutoControlException as error:
            self._failed(str(error))

    def _start_generate(self) -> None:
        self._start("generate")

    def _import_candidate(self) -> None:
        if self._on_import is None:
            self._set_status("no_import")
        elif self._candidate is None:
            self._set_status("review_required")
        elif not self._candidate.actions:
            self._set_status("empty")
        else:
            self._start("import")

    def _export(self) -> None:
        if self._candidate is None:
            self._set_status("review_required")
            return
        if self._handle is not None:
            return
        try:
            authorize_command("AC_generate_candidate_from_log")
            path, _ = QFileDialog.getSaveFileName(self, _t("export"), "candidate.zip", "ZIP (*.zip)")
            if path:
                self._start("export", path)
        except AutoControlException as error:
            self._failed(str(error))

    def _start(self, operation: CandidateOperation, output: str = "") -> None:
        if self._handle is not None:
            return
        self._generation += 1
        self._operation = operation
        if operation == "generate":
            self._candidate = None
            for view in (self._code, self._diff, self._manifest, self._warnings):
                view.clear()
        task = JournalCandidateTask(self._generation, operation, output or self._path.text().strip(),
                                      self._run_id.text(), self._target.currentText(), self._style.currentText(),
                                      self._baseline, self._candidate)
        worker = JournalCandidateWorker(task)
        self._worker = worker
        worker.progress.connect(self._progress)
        # pylint: disable-next=no-member  # reason: PySide binds this Qt signal at runtime
        self.destroyed.connect(worker.request_stop)
        self._busy(True)
        self._set_status("running")
        self._handle = start_worker(self, worker, on_done=self._received,
                                     on_thread_done=self._thread_done, on_fail=self._failed)

    def _busy(self, busy: bool) -> None:
        for control in (self._path, self._run_id, self._target, self._style):
            control.setEnabled(not busy)

    @Slot(int, int)
    def _progress(self, request_id: int, count: int) -> None:
        if request_id == self._generation and self._status_key != "cancelling":
            self._set_status("progress", str(count))

    def _received(self, outcome: JournalCandidateOutcome) -> None:
        if outcome.request_id != self._generation:
            return
        if outcome.status != "ok":
            if outcome.status == "error":
                self._failed(outcome.error)
            else:
                self._set_status("cancelled")
            return
        try:
            self._apply_result(outcome)
        except (AutoControlException, ValueError, TypeError, RuntimeError) as error:
            self._failed(str(error))

    def _apply_result(self, outcome: JournalCandidateOutcome) -> None:
        self._candidate = outcome.candidate
        if self._operation == "export":
            self._set_status("exported", outcome.output)
        elif self._operation == "import":
            authorize_command("AC_generate_candidate_from_log")
            if self._on_import is None or self._candidate is None:
                raise CandidateGenerationError("candidate import has no destination")
            self._on_import(self._candidate)
            self._set_status("imported")
        else:
            for key, view in (("code", self._code), ("diff", self._diff),
                               ("manifest", self._manifest), ("warnings", self._warnings)):
                view.setPlainText(outcome.views[key])
            self._set_status("ready_truncated" if outcome.truncated else "ready")

    def cancel(self) -> None:
        """Request stop; completed atomic exports remain committed."""
        if self._worker is not None:
            self._worker.request_stop()
            self._set_status("cancelling")

    def _thread_done(self) -> None:
        self._worker = self._handle = None
        self._busy(False)
        if self._status_key in ("running", "progress", "cancelling"):
            self._set_status("interrupted")

    def _failed(self, error: str) -> None:
        self._candidate = None
        for view in (self._code, self._diff, self._manifest, self._warnings):
            view.clear()
        self._set_status("error", scrub_secret_text(error))

    # pylint: disable-next=invalid-name  # reason: Qt override
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Cancel work and discard late results when the view closes."""
        self.cancel()
        self._generation += 1
        super().closeEvent(event)
