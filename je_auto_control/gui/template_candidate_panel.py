"""Reviewed template thumbnails, fixed-frame eligibility and explicit version transitions."""
import json
from functools import partial
from typing import Callable, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.template_candidate_worker import (
    CandidateOperation, TemplateCandidateOutcome, TemplateCandidateRequest, TemplateCandidateWorker,
)
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.policy import authorize_command

_OPERATIONS: tuple[CandidateOperation, ...] = ("create", "preview", "verify", "accept", "revert")


def _t(key: str) -> str:
    return language_wrapper.translate("template_candidate_" + key)


# pylint: disable-next=too-many-instance-attributes  # reason: form controls, preview views and one owned task
class TemplateCandidatePanel(TranslatableMixin, QWidget):
    """Operate only through Actions, with a concrete reviewed revision before file transitions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._generation = 0
        self._updating = False
        self._operation: CandidateOperation = "preview"
        self._handle: Optional[WorkerHandle] = None
        self._worker: Optional[TemplateCandidateWorker] = None
        self._template, self._candidate, self._bundle, self._dataset = (QLineEdit() for _ in range(4))
        self._revision = QLineEdit()
        self._revision.setReadOnly(True)
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0, 1)
        self._threshold.setDecimals(3)
        self._threshold.setSingleStep(0.05)
        self._threshold.setValue(0.9)
        self._original, self._replacement = QLabel(), QLabel()
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._status_key, self._status_value = "idle", ""
        self._build_layout()
        for control in (self._template, self._candidate, self._bundle):
            # pylint: disable-next=no-member  # reason: PySide signals are provided at runtime
            control.textChanged.connect(self._inputs_changed)
        # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
        self._threshold.valueChanged.connect(self._inputs_changed)
        # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
        self._dataset.textChanged.connect(self._dataset_changed)
        self.retranslate()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._tr(QLabel(), "template_candidate_explanation"))
        form = QFormLayout()
        for key, control in (("template", self._template), ("candidate", self._candidate),
                             ("bundle", self._bundle), ("dataset", self._dataset),
                             ("threshold", self._threshold), ("revision", self._revision)):
            form.addRow(self._tr(QLabel(), "template_candidate_" + key), control)
        root.addLayout(form)
        images = QHBoxLayout()
        for key, label in (("original", self._original), ("replacement", self._replacement)):
            view = QVBoxLayout()
            view.addWidget(self._tr(QLabel(), "template_candidate_" + key))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(110)
            label.setMaximumHeight(270)
            view.addWidget(label)
            images.addLayout(view)
        root.addLayout(images)
        root.addWidget(self._details, stretch=1)
        root.addWidget(self._status)

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Expose bundle creation/review/transitions and file selection through Actions."""
        actions = [("template_candidate_" + operation, partial(self._start, operation)) for operation in _OPERATIONS]
        return actions + [("template_candidate_cancel", self.cancel),
                          ("template_candidate_browse_template", partial(self._browse, "template")),
                          ("template_candidate_browse_candidate", partial(self._browse, "candidate")),
                          ("template_candidate_browse_bundle", partial(self._browse, "bundle")),
                          ("template_candidate_browse_dataset", partial(self._browse, "dataset"))]

    def retranslate(self) -> None:
        """Keep preview state and the active operation while translating labels."""
        TranslatableMixin.retranslate(self)
        self._set_status(self._status_key, self._status_value)

    def _set_status(self, key: str, value: str = "") -> None:
        self._status_key, self._status_value = key, value
        self._status.setText(_t(key).replace("{value}", value))

    def _inputs_changed(self, *_args) -> None:
        if self._updating:
            return
        self.cancel()
        self._generation += 1
        self._revision.clear()
        self._original.clear()
        self._replacement.clear()
        self._details.clear()
        self._set_status("idle")

    def _dataset_changed(self, *_args) -> None:
        if not self._updating:
            self.cancel()
            self._generation += 1
            self._details.clear()
            self._set_status("idle")

    def _browse(self, name: str) -> None:
        if self._handle is not None:
            return
        try:
            authorize_command("AC_template_candidate_preview")
        except AutoControlException as error:
            self._failed(str(error))
            return
        control = {"template": self._template, "candidate": self._candidate,
                   "bundle": self._bundle, "dataset": self._dataset}[name]
        if name == "bundle":
            path, _ = QFileDialog.getSaveFileName(self, _t("bundle"), control.text(), "JSON (*.json);;All (*)",
                                                  options=QFileDialog.Option.DontConfirmOverwrite)
        else:
            filters = "JSON (*.json);;All (*)" if name == "dataset" else "Images (*.png *.jpg *.bmp);;All (*)"
            path, _ = QFileDialog.getOpenFileName(self, _t(name), control.text(), filters)
        if path:
            control.setText(path)

    def _start(self, operation: CandidateOperation) -> None:
        if self._handle is not None:
            return
        if operation in ("accept", "revert") and not self._revision.text():
            self._set_status("review_required")
            return
        self._generation += 1
        self._operation = operation
        self._details.clear()
        request = TemplateCandidateRequest(self._generation, operation, self._template.text().strip(),
                                             self._candidate.text().strip(), self._bundle.text().strip(),
                                             self._dataset.text().strip(), self._revision.text(),
                                             float(self._threshold.value()))
        worker = TemplateCandidateWorker(request)
        self._worker = worker
        worker.progress.connect(self._progress)
        # pylint: disable-next=no-member  # reason: PySide binds this signal at runtime
        self.destroyed.connect(worker.request_stop)
        self._set_busy(True)
        self._set_status("running")
        self._handle = start_worker(self, worker, on_done=self._received,
                                    on_thread_done=self._thread_done, on_fail=self._failed)

    def cancel(self) -> None:
        """Request cooperative stop; an already committed transition remains committed."""
        if self._worker is not None:
            self._worker.request_stop()
            self._set_status("cancelling")

    def _set_busy(self, busy: bool) -> None:
        for control in (self._template, self._candidate, self._bundle, self._dataset, self._threshold):
            control.setEnabled(not busy)

    @Slot(int, int)
    def _progress(self, request_id: int, count: int) -> None:
        if request_id == self._generation and self._status_key != "cancelling":
            self._set_status("progress", str(count))

    def _received(self, outcome: TemplateCandidateOutcome) -> None:
        if outcome.request_id != self._generation:
            return
        if outcome.status == "cancelled":
            self._set_status("cancelled")
            return
        if outcome.status == "error":
            self._failed(outcome.error)
            return
        self._apply_result(outcome)

    def _apply_result(self, outcome: TemplateCandidateOutcome) -> None:
        self._details.setPlainText(json.dumps(outcome.data, ensure_ascii=False, indent=2))
        if outcome.preview is not None:
            self._show_preview(outcome)
        elif outcome.state is not None and self._revision.text() != outcome.state.revision:
            self._revision.clear()
            self._original.clear()
            self._replacement.clear()
        if self._operation == "verify" and outcome.data is not None:
            eligible = outcome.data.get("eligible") is True
            self._set_status("eligible" if eligible else "ineligible")
        else:
            self._set_status("created" if self._operation == "create" else "done")

    def _show_preview(self, outcome: TemplateCandidateOutcome) -> None:
        preview = outcome.preview
        if preview is None:
            return
        self._updating = True
        try:
            self._template.setText(preview.state.template_path)
            self._threshold.setValue(preview.state.threshold)
            self._revision.setText(preview.state.revision)
        finally:
            self._updating = False
        for label, data in ((self._original, preview.original_png), (self._replacement, preview.candidate_png)):
            image = QPixmap()
            image.loadFromData(data)
            label.setPixmap(image.scaled(400, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))

    def _thread_done(self) -> None:
        self._handle = self._worker = None
        self._set_busy(False)
        if self._status_key in ("running", "progress", "cancelling"):
            self._set_status("interrupted")

    def _failed(self, error: str) -> None:
        self._details.clear()
        self._revision.clear()
        self._original.clear()
        self._replacement.clear()
        self._set_status("error", scrub_secret_text(error))

    # pylint: disable-next=invalid-name  # reason: Qt override
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Discard stale responses and request cancellation before the view closes."""
        self.cancel()
        self._generation += 1
        super().closeEvent(event)
