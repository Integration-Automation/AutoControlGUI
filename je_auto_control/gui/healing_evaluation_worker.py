"""Cancellable fixed-frame comparisons retaining their registrant's context and authority."""
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
from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text, is_run_interruption
from je_auto_control.utils.self_healing.evaluation import HealingComparison
from je_auto_control.utils.self_healing.evaluation_io import evaluate_healing_manifest


@dataclass(frozen=True)
class HealingEvaluationOutcome:
    """One terminal result; interrupted work never publishes a partial comparison."""

    request_id: int
    status: Literal["ok", "cancelled", "error"]
    report: Optional[HealingComparison] = None
    error: str = ""


class HealingEvaluationWorker(QObject):
    """Perform local comparison off the GUI thread with cooperative checkpoints."""

    finished = Signal(object)

    def __init__(self, request_id: int, path: str) -> None:
        super().__init__()
        self._request_id, self._path = request_id, path
        self._stop = Event()
        self._context = copy_context()
        self._authority = DeferredAuthorization.capture()

    @Slot()
    def request_stop(self) -> None:
        """Request stop between file reads and comparison pairs without blocking Qt."""
        self._stop.set()

    def _checkpoint(self, _count: int) -> None:
        if self._stop.is_set():
            raise CancelledError()

    @Slot()
    def run(self) -> None:
        """Emit a terminal outcome under the captured caller context."""
        self.finished.emit(self._context.run(self._evaluate))

    def _evaluate(self) -> HealingEvaluationOutcome:
        try:
            self._checkpoint(0)
            with self._authority.scope():
                report = evaluate_healing_manifest(self._path, observer=self._checkpoint)
            self._checkpoint(0)
        except (CancelledError, AsyncCancelledError):
            return HealingEvaluationOutcome(self._request_id, "cancelled")
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            if is_run_interruption(error):
                return HealingEvaluationOutcome(self._request_id, "cancelled")
            return HealingEvaluationOutcome(self._request_id, "error",
                                             error=scrub_secret_text(_ordinary_error_text(error)))
        return HealingEvaluationOutcome(self._request_id, "ok", report)
