"""Explicit transfer requests and consent preparation with revision-bound background observations."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable
import json

from PySide6 import QtWidgets

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.task_controller import TaskController, TaskOutcome
from je_auto_control.utils.agent_runtime.api import manage_agent_transfer
from je_auto_control.utils.agent_runtime.transfer_operations import OPERATIONS
from je_auto_control.utils.exception.cancellation import CancellationToken


def _translate(key: str) -> str:
    return language_wrapper.translate(key, key)


def _request(operation: str, request: dict, token: CancellationToken) -> dict:
    token.checkpoint()
    return manage_agent_transfer(operation, request)


def _connect(signal: Any, callback: Callable[..., None]) -> None:
    """Connect a compiled Qt signal descriptor at the binding's dynamically typed boundary."""
    signal.connect(callback)


@dataclass
class _ViewState:
    handle: Any = None
    generation: int = 0
    submitted: int = -1
    closed: bool = False
    review: tuple[str, dict, dict] | None = None
    labels: list[tuple[QtWidgets.QLabel, str]] = field(default_factory=list)


class AgentTransferView(QtWidgets.QWidget):
    """Observe finite service requests; closing the view never cancels a durable import or grant."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('agent_transfer_view')
        self._controller = TaskController(self)
        self._state = _ViewState()
        self._operation = QtWidgets.QComboBox()
        for operation in OPERATIONS:
            self._operation.addItem('', operation)
        self._request = QtWidgets.QPlainTextEdit('{}')
        self._result = QtWidgets.QPlainTextEdit()
        self._result.setReadOnly(True)
        self._notice = QtWidgets.QLabel()
        self._notice.setWordWrap(True)
        self._status = QtWidgets.QLabel()
        form = QtWidgets.QFormLayout()
        for key, control in (('operation', self._operation), ('request', self._request), ('result', self._result)):
            label = QtWidgets.QLabel()
            self._state.labels.append((label, 'agent_transfer_' + key))
            form.addRow(label, control)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._notice)
        layout.addLayout(form)
        layout.addWidget(self._status)
        _connect(self._operation.currentIndexChanged, self.invalidate)
        _connect(self._request.textChanged, self.invalidate)
        self.retranslate()

    def retranslate(self) -> None:
        """Translate labels without sending a request or changing an approval's revision."""
        for label, key in self._state.labels:
            label.setText(_translate(key))
        for index in range(self._operation.count()):
            self._operation.setItemText(index, _translate('agent_transfer_op_' + self._operation.itemData(index)))
        self._notice.setText(_translate('agent_transfer_notice'))

    def invalidate(self, *_args: object) -> None:
        """Reject late replies even when a changed selection is subsequently restored."""
        self._state.generation += 1
        self._state.review = None
        self._result.clear()
        self._status.clear()

    def detach(self) -> None:
        """Abandon GUI delivery; the service retains ownership of already accepted durable work."""
        self._state.closed = True
        self.invalidate()
        self._controller.close()

    def menu_actions(self) -> list:
        """Expose explicit dispatch and editable preparation only through the common Actions menu."""
        return [('agent_transfer_apply', self.apply), ('agent_transfer_prepare_approval', self.prepare_approval),
                *[('agent_transfer_example_' + name, partial(self.example, name)) for name in
                  ('source', 'destination', 'evidence')]]

    def apply(self) -> None:
        """Send one finite request after JSON and explicit approval-note checks."""
        if self._state.closed:
            return
        operation = self._operation.currentData()
        try:
            request = json.loads(self._request.toPlainText())
            if not isinstance(request, dict):
                raise ValueError('transfer request must be a JSON object')
            note = request.get('note')
            if operation.startswith('create_') and (not isinstance(note, str) or not note.strip()):
                raise ValueError(_translate('agent_transfer_note_required'))
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        if self._state.handle is not None and self._state.handle.outcome is None:
            return
        self._state.submitted = self._state.generation
        self._state.review = None
        self._result.clear()
        self._status.clear()
        self._state.handle = self._controller.submit(partial(_request, operation, request), owner=self)
        self._state.handle.finished.connect(self._completed)

    def _completed(self, outcome: TaskOutcome) -> None:
        if (self._state.closed or self._state.handle is None or outcome.task_id != self._state.handle.task_id
                or self._state.submitted != self._state.generation):
            return
        if outcome.status != 'ok':
            self._status.setText(outcome.error or outcome.status)
            return
        self._result.setPlainText(json.dumps(outcome.value, ensure_ascii=False, indent=2))
        self._remember_review(outcome.value)

    def _remember_review(self, value: object) -> None:
        operation = self._operation.currentData()
        if operation.startswith('review_') and isinstance(value, dict):
            if value.get('approval_required') is True and isinstance(value.get('review'), str):
                self._state.review = (operation, json.loads(self._request.toPlainText()), value)

    def prepare_approval(self) -> None:
        """Prepare an empty-note create request only from this unchanged view's actual review response."""
        if self._state.closed or self._state.review is None:
            self._status.setText(_translate('agent_transfer_review_required'))
            return
        operation, original, reviewed = self._state.review
        request = {'review': reviewed['review'], 'idempotency_key': original.get('idempotency_key', ''), 'note': ''}
        if 'host' in original:
            request['host'] = original['host']
        self._operation.setCurrentIndex(self._operation.findData(operation.replace('review_', 'create_', 1)))
        self._request.setPlainText(json.dumps(request, ensure_ascii=False, indent=2))

    def example(self, name: str) -> None:
        """Prepare placeholders without inferring a host, grant, recipient, directory or consent."""
        if self._state.closed:
            return
        examples: dict[str, tuple[str, dict[str, Any]]] = {
            'source': ('review_export', {'source_task': '<source-task-id>',
                'selection': [{'criterion': 0, 'names': []}], 'recipient_policy': 'caller'}),
            'destination': ('review_import', {'source_host': '<registered-source-host>', 'export_id': '<export-id>',
                'target': '<destination-file-target>', 'directory': '<approved-destination-directory>'}),
            'evidence': ('review_evidence', {'source_task': '<original-source-task-id>',
                'task_id': '<final-evidence-task-id>', 'recipient_policy': 'caller'}),
        }
        operation, request = examples[name]
        request['idempotency_key'] = '<idempotency-key>'
        self._operation.setCurrentIndex(self._operation.findData(operation))
        self._request.setPlainText(json.dumps(request, ensure_ascii=False, indent=2))
