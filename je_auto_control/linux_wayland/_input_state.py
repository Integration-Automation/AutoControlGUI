"""Classify native input authority failures without treating them as optional backend absence."""
from dataclasses import dataclass
from typing import Optional

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException

_STATES = frozenset({'unavailable', 'needs_permission', 'paused', 'revoked', 'failed'})


@dataclass(frozen=True)
class InputFailure:
    """Inert failure metadata; no native handle, exception traceback or permission request is retained."""
    state: str
    backend: str
    message: str
    capability: str = 'input'
    fallback_allowed: bool = True

    def __post_init__(self) -> None:
        if (not isinstance(self.state, str) or self.state not in _STATES
                or not isinstance(self.backend, str) or self.backend not in ('libei', 'portal')
                or not isinstance(self.fallback_allowed, bool)):
            raise AutoControlException('invalid Wayland input failure state')
        if self.state != 'unavailable':
            object.__setattr__(self, 'fallback_allowed', False)


def blocked_input(error: BaseException) -> Optional[tuple[BaseException, InputFailure]]:
    """Find an explicit authority/protocol refusal through bounded wrappers, preserving original controls first."""
    raise_caused_run_interruption(error)
    current: Optional[BaseException] = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(seen) < 64:
        seen.add(id(current))
        status = getattr(current, 'status', None)
        if isinstance(status, InputFailure) and (status.state != 'unavailable' or not status.fallback_allowed):
            return current, status
        current = current.__cause__
    return None


def raise_if_input_blocked(error: BaseException) -> None:
    """Refuse implicit CLI fallback after native permission/session failure or explicit cancellation."""
    blocked = blocked_input(error)
    if blocked is not None:
        raise blocked[0]
