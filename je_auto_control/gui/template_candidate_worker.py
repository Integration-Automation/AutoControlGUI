"""Context-preserving, cancellable candidate-file operations outside the GUI thread."""
from asyncio import CancelledError as AsyncCancelledError
from concurrent.futures import CancelledError
from contextvars import copy_context
from dataclasses import dataclass
from threading import Event
from typing import Literal, Optional

from PySide6.QtCore import QObject, Signal, Slot

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text, is_run_interruption
from je_auto_control.utils.self_healing.template_candidates import (
    accept_template_candidate, preview_template_candidate, revert_template_candidate, verify_template_candidate,
)
from je_auto_control.utils.self_healing.template_commands import _create_from_file
from je_auto_control.utils.self_healing.template_models import (
    TemplateCandidatePreview, TemplateCandidateState, TemplateRevisionError,
)

CandidateOperation = Literal["create", "preview", "verify", "accept", "revert"]


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable form snapshot, not mutable services
class TemplateCandidateRequest:
    """One explicit operation and its review-bound input values."""

    request_id: int
    operation: CandidateOperation
    template_path: str
    candidate_path: str
    bundle_path: str
    dataset_path: str
    expected_revision: str
    threshold: float


@dataclass(frozen=True)
class TemplateCandidateOutcome:
    """Terminal operation data; thumbnails are provided only by explicit preview."""

    request_id: int
    status: Literal["ok", "cancelled", "error"]
    data: Optional[dict[str, object]] = None
    state: Optional[TemplateCandidateState] = None
    preview: Optional[TemplateCandidatePreview] = None
    error: str = ""


class TemplateCandidateWorker(QObject):
    """Run under captured authority; cancellation checkpoints stop before atomic writes."""

    finished = Signal(object)
    progress = Signal(int, int)

    def __init__(self, request: TemplateCandidateRequest) -> None:
        super().__init__()
        self._request = request
        self._stop = Event()
        self._context = copy_context()
        self._authority = DeferredAuthorization.capture()
        self._last_count = 0

    @Slot()
    def request_stop(self) -> None:
        """Request cooperative stop before the next candidate operation checkpoint."""
        self._stop.set()

    def _checkpoint(self, count: int) -> None:
        if self._stop.is_set():
            raise CancelledError()
        self._last_count = max(self._last_count, count)
        self.progress.emit(self._request.request_id, self._last_count)

    @Slot()
    def run(self) -> None:
        """Emit one outcome; a successful committed write is never relabelled cancelled afterward."""
        self.finished.emit(self._context.run(self._perform))

    def _perform(self) -> TemplateCandidateOutcome:
        request = self._request
        try:
            self._checkpoint(0)
            with self._authority.scope():
                authorize_command(f"AC_template_candidate_{request.operation}")
                data, state, preview = self._operate()
        except (CancelledError, AsyncCancelledError):
            return TemplateCandidateOutcome(request.request_id, "cancelled")
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            if is_run_interruption(error):
                return TemplateCandidateOutcome(request.request_id, "cancelled")
            return TemplateCandidateOutcome(request.request_id, "error",
                                              error=scrub_secret_text(_ordinary_error_text(error)))
        return TemplateCandidateOutcome(request.request_id, "ok", data, state, preview)

    def _operate(self) -> tuple[dict[str, object], TemplateCandidateState, Optional[TemplateCandidatePreview]]:
        request = self._request
        if request.operation == "create":
            created = _create_from_file(request.template_path, request.candidate_path, request.bundle_path,
                                         request.threshold, observer=self._checkpoint)
            return created.to_dict(), created, None
        if request.operation == "preview":
            preview = preview_template_candidate(request.bundle_path, observer=self._checkpoint)
            self._checkpoint(self._last_count)
            return preview.to_dict(), preview.state, preview
        if request.operation == "verify":
            verified = verify_template_candidate(request.bundle_path, request.dataset_path, observer=self._checkpoint)
            self._checkpoint(self._last_count)
            return verified.to_dict(), verified.state, None
        if request.operation == "accept":
            accepted = accept_template_candidate(request.bundle_path, request.dataset_path, request.expected_revision,
                                                   observer=self._checkpoint)
            return accepted.to_dict(), accepted.state, None
        if request.operation == "revert":
            reverted = revert_template_candidate(request.bundle_path, request.expected_revision,
                                                   observer=self._checkpoint)
            return reverted.to_dict(), reverted.state, None
        raise TemplateRevisionError("unknown candidate operation")
