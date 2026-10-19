"""Background journal review, diff rendering, export and import validation with captured authority."""
import difflib
import json
from asyncio import CancelledError as AsyncCancelledError
from concurrent.futures import CancelledError
from contextvars import copy_context
from dataclasses import dataclass, field
from hashlib import sha256
from threading import Event
from typing import Literal, Optional, cast

from PySide6.QtCore import QObject, Signal, Slot

from je_auto_control.utils.action_journal.events import ActionEvent
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.codegen.candidate_archive import validate_candidate_review, write_candidate_archive
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError, CandidateScript
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_data, scrub_secret_text
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text, is_run_interruption

CandidateOperation = Literal["generate", "export", "import"]
_PREVIEW_LIMIT = 200000


def baseline_snapshot(actions: list[list[object]]) -> tuple[str, str]:
    """Seal the exact editor state while returning only sanitized JSON for the visible diff."""
    try:
        token = sha256(json.dumps(actions, allow_nan=False).encode("utf-8")).hexdigest()
        wire = sanitize_event(ActionEvent("preview", "baseline", "<baseline>", {"actions": actions}, 0.0))
        params = cast(dict[str, object], wire["parameters"])
        rendered = json.dumps(scrub_secret_data(params["actions"]), indent=2, ensure_ascii=True)
    except (TypeError, ValueError, RecursionError):
        raise CandidateGenerationError("current editor actions cannot be safely snapshotted") from None
    return rendered, token


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable input values for three explicit task kinds
class JournalCandidateTask:
    """A generation ID and captured inputs; exporting/importing uses the cached reviewed candidate."""

    request_id: int
    operation: CandidateOperation
    path: str
    run_id: str = ""
    target: str = "pytest"
    style: str = "actions"
    baseline: str = "[]"
    candidate: Optional[CandidateScript] = None


@dataclass(frozen=True)
class JournalCandidateOutcome:
    """One terminal result; cancelled work never publishes partial source or a false export verdict."""

    request_id: int
    status: Literal["ok", "cancelled", "error"]
    candidate: Optional[CandidateScript] = None
    views: dict[str, str] = field(default_factory=dict)
    output: str = ""
    error: str = ""
    truncated: bool = False


class JournalCandidateWorker(QObject):
    """Run under the registrant's authority and context, with stop checks before irreversible export."""

    finished = Signal(object)
    progress = Signal(int, int)

    def __init__(self, task: JournalCandidateTask) -> None:
        super().__init__()
        self._task = task
        self._count = 0
        self._stop = Event()
        self._context = copy_context()
        self._authority = DeferredAuthorization.capture()

    @Slot()
    def request_stop(self) -> None:
        """Request cooperative cancellation without blocking the GUI."""
        self._stop.set()

    def _checkpoint(self, count: int) -> None:
        if self._stop.is_set():
            raise CancelledError()
        self._count = max(self._count, count)
        if self._count % 100 == 0:
            self.progress.emit(self._task.request_id, self._count)

    @Slot()
    def run(self) -> None:
        """Emit one result under captured authority; successful committed exports stay successful."""
        self.finished.emit(self._context.run(self._perform))

    def _perform(self) -> JournalCandidateOutcome:
        try:
            self._checkpoint(0)
            with self._authority.scope():
                authorize_command("AC_generate_candidate_from_log")
                return self._operate()
        except (CancelledError, AsyncCancelledError):
            return JournalCandidateOutcome(self._task.request_id, "cancelled")
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            if is_run_interruption(error):
                return JournalCandidateOutcome(self._task.request_id, "cancelled")
            return JournalCandidateOutcome(self._task.request_id, "error",
                                              error=scrub_secret_text(_ordinary_error_text(error)))

    def _operate(self) -> JournalCandidateOutcome:
        task = self._task
        if task.operation == "generate":
            candidate = generate_candidate_from_log(task.path, run_id=task.run_id, target=task.target,
                                                       style=task.style, observer=self._checkpoint)
            views, truncated = _render(candidate, task.baseline)
            self._checkpoint(self._count)
            validate_candidate_review(candidate)
            return JournalCandidateOutcome(task.request_id, "ok", candidate, views, truncated=truncated)
        reviewed = task.candidate
        if reviewed is None:
            raise CandidateGenerationError("a reviewed candidate is required")
        if task.operation == "export":
            output = write_candidate_archive(reviewed, task.path, observer=self._checkpoint)
            return JournalCandidateOutcome(task.request_id, "ok", reviewed, output=str(output))
        if task.operation == "import":
            validate_candidate_review(reviewed)
            self._checkpoint(self._count)
            validate_candidate_review(reviewed)
            return JournalCandidateOutcome(task.request_id, "ok", reviewed)
        raise CandidateGenerationError("unknown journal candidate operation")


def _render(candidate: CandidateScript, baseline: str) -> tuple[dict[str, str], bool]:
    data = candidate.to_dict()
    actions = json.dumps(data["actions"], indent=2, ensure_ascii=True)
    difference = "".join(difflib.unified_diff((baseline + "\n").splitlines(keepends=True),
                                              (actions + "\n").splitlines(keepends=True),
                                              fromfile="current-actions.json", tofile="candidate-actions.json"))
    views = {"code": candidate.code, "diff": difference,
             "manifest": json.dumps(data["manifest"], indent=2, ensure_ascii=True),
             "warnings": "\n".join(candidate.warnings)}
    truncated = any(len(value) > _PREVIEW_LIMIT for value in views.values())
    return {key: value[:_PREVIEW_LIMIT] for key, value in views.items()}, truncated
