"""Decode complete Android command phases without claiming input retirement or task completion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from je_auto_control.utils.agent_runtime.android_transport import AdbShellResult
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

ACTION_HEADER = b"__JE_ANDROID_ACTION_V2__\n"
ACTION_ATTEMPTED = ACTION_HEADER + b"attempted\n"
ACTION_RETURNED = ACTION_ATTEMPTED + b"returned\n"
ACTION_MARKER = ACTION_RETURNED + b"verified\n"


@dataclass(frozen=True)
class AndroidActionResult:
    """A complete script phase; even returned input does not certify remote queues or held keys."""

    phase: Literal["pre_input_refused", "input_failed", "post_input_refused", "input_returned"]
    returncode: int

    @property
    def may_have_effect(self) -> bool:
        """Only a complete closed pre-input refusal proves this command never invoked input."""
        return self.phase != "pre_input_refused"


def parse_android_action_result(result: AdbShellResult) -> AndroidActionResult:
    """Require complete shell-v2 EOF/exit evidence, exact phases and no untrusted diagnostics.

    Call only after the managed transport has returned a complete result. A transport exception,
    truncated output, malformed phase or mismatched exit is unknown, never a no-effect certificate.
    No parsed phase authorizes retries, releases a remote journal or proves task completion.
    """
    if not isinstance(result, AdbShellResult):
        raise AgentTaskError("Android action result is unknown; complete transport evidence is required")
    if (not isinstance(result.returncode, int) or isinstance(result.returncode, bool)
            or not isinstance(result.stdout, bytes) or not isinstance(result.stderr, bytes) or result.stderr):
        raise AgentTaskError("Android action result is unknown; complete closed evidence is required")
    expected = _action_outcomes()
    phase = expected.get((result.stdout, result.returncode))
    if phase is None:
        raise AgentTaskError("Android action result is unknown; phase or exit evidence is incompatible")
    return AndroidActionResult(phase, result.returncode)


def _action_outcomes() -> dict[tuple[bytes, int], Literal[
        "pre_input_refused", "input_failed", "post_input_refused", "input_returned"]]:
    outcomes: dict[tuple[bytes, int], Literal[
        "pre_input_refused", "input_failed", "post_input_refused", "input_returned"]] = {
        (ACTION_MARKER, 0): "input_returned",
        (ACTION_ATTEMPTED + b"input_failed\n", 94): "input_failed",
    }
    for code in (91, 92, 93, 95):
        outcomes[(ACTION_HEADER + f"refused:{code}\n".encode("ascii"), code)] = "pre_input_refused"
    for code in (91, 92, 93):
        outcomes[(ACTION_RETURNED + f"post_refused:{code}\n".encode("ascii"), code)] = "post_input_refused"
    return outcomes
