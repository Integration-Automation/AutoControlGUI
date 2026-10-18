"""Explicit immutable self-healing requests and post-click verification choices."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.self_healing.heal_log import HealEventLog
from je_auto_control.utils.vision.backends.base import VLMBackend


class SelfHealRequestError(AutoControlException, ValueError):
    """A self-healing request cannot be executed safely as configured."""


def _text(value: Optional[str], label: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip() or "\x00" in value):
        raise SelfHealRequestError(f"{label} must be nonempty text or null")


def _region(value: Optional[Sequence[int]]) -> Optional[tuple[int, int, int, int]]:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise SelfHealRequestError("screen_region requires four integer bbox coordinates")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise SelfHealRequestError("screen_region requires four integer bbox coordinates")
    left, top, right, bottom = value
    if right <= left or bottom <= top:
        raise SelfHealRequestError("screen_region must have positive area")
    return left, top, right, bottom


@dataclass(frozen=True)
class VerificationRequest:
    """Choose exactly one Python bool callback or configured VLM post-condition.

    A VLM check takes fresh logical pixels after dispatch. Its region defaults to
    the primary request, independently of the locator region. Model defaults may
    inherit the locator's explicit model. Callback configuration never selects a backend.
    """

    description: Optional[str] = None
    verifier: Optional[Callable[[], bool]] = field(default=None, repr=False)
    backend: Optional[VLMBackend] = field(default=None, repr=False)
    model: Optional[str] = None
    screen_region: Optional[Sequence[int]] = None

    def __post_init__(self) -> None:
        _text(self.description, "verification description")
        _text(self.model, "verification model")
        if (self.description is None) == (self.verifier is None):
            raise SelfHealRequestError("choose one verification description or callback")
        if self.verifier is not None:
            self._check_callback()
        elif self.backend is not None and not isinstance(self.backend, VLMBackend):
            raise SelfHealRequestError("verification backend must implement VLMBackend")
        object.__setattr__(self, "screen_region", _region(self.screen_region))

    def _check_callback(self) -> None:
        if not callable(self.verifier):
            raise SelfHealRequestError("verifier must be callable")
        if self.backend is not None or self.model is not None or self.screen_region is not None:
            raise SelfHealRequestError("callback verification cannot configure VLM options")


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable public request values, not mutable services
class SelfHealRequest:
    """Run explicit locate/click behavior; verification requires an explicit click operation."""

    template_path: Optional[str] = None
    description: Optional[str] = None
    detect_threshold: float = 0.9
    screen_region: Optional[Sequence[int]] = None
    model: Optional[str] = None
    operation: Literal["locate", "click"] = "locate"
    mouse_keycode: str = "mouse_left"
    verification: Optional[VerificationRequest] = None
    log: Optional[HealEventLog] = field(default=None, repr=False)
    raise_on_miss: bool = False

    def __post_init__(self) -> None:
        for label in ("template_path", "description", "model", "mouse_keycode"):
            _text(getattr(self, label), label)
        if self.template_path is None and self.description is None:
            raise SelfHealRequestError("template_path or description is required")
        self._check_operation()
        self._check_threshold()
        if not isinstance(self.raise_on_miss, bool):
            raise SelfHealRequestError("raise_on_miss must be boolean")
        if self.log is not None and not isinstance(self.log, HealEventLog):
            raise SelfHealRequestError("log must be a HealEventLog")
        object.__setattr__(self, "screen_region", _region(self.screen_region))

    def _check_operation(self) -> None:
        if not isinstance(self.mouse_keycode, str) or not self.mouse_keycode.strip():
            raise SelfHealRequestError("mouse_keycode must be nonempty text")
        if self.operation not in ("locate", "click"):
            raise SelfHealRequestError("operation must be locate or click")
        if self.verification is not None:
            if not isinstance(self.verification, VerificationRequest) or self.operation != "click":
                raise SelfHealRequestError("verification requires a VerificationRequest and click operation")

    def _check_threshold(self) -> None:
        if isinstance(self.detect_threshold, bool) or not isinstance(self.detect_threshold, (int, float)):
            raise SelfHealRequestError("detect_threshold must be a finite number from 0 to 1")
        if not 0 <= self.detect_threshold <= 1:
            raise SelfHealRequestError("detect_threshold must be a finite number from 0 to 1")
