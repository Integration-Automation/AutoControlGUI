"""Where each Wayland authorisation stands, as an explicit state.

Input and capture on Wayland both hang off something the user or the
compositor can take away: a consent dialog, a portal session, the compositor
process itself. Until now none of that was written down anywhere. A dismissed
consent dialog became ``LibeiUnavailable``, which ``keyboard`` and ``mouse``
read as "use ydotool" — so the user said no to remote control and the desktop
was driven through ``/dev/uinput`` anyway, and nothing an operator could look
at said which of the two had happened.

This module is the record. It holds no handles and performs no I/O beyond one
``os.stat`` of the compositor's socket: the modules that own the sessions
report transitions here, and :mod:`je_auto_control.wrapper.capabilities` reads
them back without asking anyone for anything.

Two channels, kept apart on purpose — a host can have working capture and no
input, or the reverse, and one diagnosis for both hides which:

``input``    the RemoteDesktop portal session libei emits through
``capture``  the Screenshot portal request (the other capture tiers need none)

Pure stdlib, importable on every platform.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException

INPUT = "input"
CAPTURE = "capture"
_CHANNELS = (INPUT, CAPTURE)

#: What an operator can do when the input session was refused or taken away.
INPUT_RECOVERY = (
    "Allow the remote-control request when the desktop asks again: call "
    "reset_input_authorisation() (AC_reset_input_authorisation, or Actions > "
    "Ask for input permission again in the Diagnostics tab), then repeat the "
    "action. To use ydotool instead of the portal, set "
    "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli before starting — that choice "
    "is never made for you after a refusal."
)

#: What an operator can do when the screenshot request was dismissed.
CAPTURE_RECOVERY = (
    "Allow the screenshot request when the desktop asks again, install a "
    "capture tool for your compositor (grim, gnome-screenshot or spectacle), "
    "or name your own command in JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND."
)


class AuthorisationState(str, Enum):
    """One step in the life of a portal request or session."""

    NOT_REQUESTED = "not_requested"
    REQUESTING = "requesting"
    GRANTED = "granted"
    #: The user (or the portal on their behalf) answered no.
    DECLINED = "declined"
    #: Nobody answered within this project's own deadline.
    TIMED_OUT = "timed_out"
    #: The request failed for a reason that is not a refusal: no portal on
    #: the bus, a portal without the interface, a broken handshake.
    FAILED = "failed"
    #: This process ended the session itself.
    CLOSED = "closed"
    #: The compositor or portal ended a session that had been granted.
    REVOKED = "revoked"


#: States after which input must not be handed to another backend. Both mean
#: "someone with the authority to say no, said no"; routing the same input
#: through ``/dev/uinput`` would make that answer meaningless.
BLOCKING_STATES = frozenset({AuthorisationState.DECLINED,
                             AuthorisationState.REVOKED})


@dataclass(frozen=True)
class AuthorisationRecord:
    """The current state of one channel, and why."""

    channel: str
    state: AuthorisationState = AuthorisationState.NOT_REQUESTED
    detail: str = ""
    #: Which compositor instance granted it — see :func:`compositor_identity`.
    compositor: Optional[str] = None

    @property
    def blocks_fallback(self) -> bool:
        """Whether another backend may take over this channel's work."""
        return self.state in BLOCKING_STATES


class WaylandAuthorisationError(AutoControlException):
    """An action was refused because its authorisation was refused or lost.

    Deliberately *not* a ``RuntimeError``: the backend probes in ``keyboard``
    and ``mouse`` catch that to mean "libei is not here, use the CLI", which
    is exactly the fallback this error exists to stop.
    """

    def __init__(self, record: AuthorisationRecord, recovery: str) -> None:
        self.state = record.state
        self.capability = record.channel
        self.recovery = recovery
        reason = record.detail or record.state.value
        super().__init__(
            f"Wayland {record.channel} is not authorised ({record.state.value}"
            f": {reason}). {recovery}")

    @property
    def has_recovery_instruction(self) -> bool:
        """Whether the error tells the operator what to do next."""
        return bool(self.recovery)


def compositor_identity(environ: Optional[Mapping[str, str]] = None
                        ) -> Optional[str]:
    """Something that changes when the compositor is restarted, or None.

    The compositor's listening socket is created when it starts, so its
    device, inode and creation time identify one compositor *process* well
    enough to notice a new one. Reads metadata only; opens nothing.
    """
    env = environ if environ is not None else os.environ
    display = (env.get("WAYLAND_DISPLAY") or "").strip()
    if not display:
        return None
    path = display if os.path.isabs(display) else os.path.join(
        env.get("XDG_RUNTIME_DIR") or "", display)
    try:
        found = os.stat(path)
    except (OSError, ValueError):
        return None
    return f"{found.st_dev}:{found.st_ino}:{found.st_ctime_ns}"


class AuthorisationLedger:
    """Thread-safe record of every channel's authorisation state.

    Emission runs on whatever thread the caller is on — the executor, a
    scheduler worker, a GUI slot — and the diagnostics tab reads from the GUI
    thread, so every access goes through one lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, AuthorisationRecord] = {
            channel: AuthorisationRecord(channel) for channel in _CHANNELS}

    def get(self, channel: str) -> AuthorisationRecord:
        """The current record of ``channel``."""
        with self._lock:
            return self._records[_known(channel)]

    def transition(self, channel: str, state: AuthorisationState,
                   detail: str = "") -> AuthorisationRecord:
        """Move ``channel`` to ``state`` and return the new record.

        A grant remembers which compositor made it, so a later probe can tell
        a session that outlived its compositor from one that is still good.
        """
        granted = state is AuthorisationState.GRANTED
        granted_by = compositor_identity() if granted else None
        with self._lock:
            current = self._records[_known(channel)]
            updated = replace(
                current, state=state, detail=detail,
                compositor=granted_by if granted else current.compositor)
            self._records[channel] = updated
            return updated

    def reset(self, channel: Optional[str] = None) -> None:
        """Forget ``channel`` (or every channel), so it may be asked again."""
        targets = _CHANNELS if channel is None else (_known(channel),)
        with self._lock:
            for name in targets:
                self._records[name] = AuthorisationRecord(name)

    def require_usable(self, channel: str, recovery: str) -> None:
        """Raise if ``channel`` was refused or revoked."""
        record = self.get(channel)
        if record.blocks_fallback:
            raise WaylandAuthorisationError(record, recovery)


def _known(channel: str) -> str:
    """Reject a channel name nobody reports, rather than inventing a record."""
    if channel not in _CHANNELS:
        raise ValueError(f"unknown authorisation channel {channel!r}")
    return channel


#: The process-wide ledger every Wayland module reports to.
ledger = AuthorisationLedger()


__all__ = [
    "AuthorisationLedger", "AuthorisationRecord", "AuthorisationState",
    "BLOCKING_STATES", "CAPTURE", "CAPTURE_RECOVERY", "INPUT",
    "INPUT_RECOVERY", "WaylandAuthorisationError", "compositor_identity",
    "ledger",
]
