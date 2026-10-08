"""Decide whether to use the native libei backend or the CLI shims.

Honours ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND``:

* ``libei`` — force the native binding; raise if libei isn't installed.
* ``cli`` — force ``wtype`` / ``ydotool`` shims.
* ``auto`` (default) — try libei first; fall back to CLI when libei cannot
  be brought up.

**"Cannot be brought up" is not "was refused".** A host without libei, without
a RemoteDesktop portal, or with a handshake that never completes falls back to
the CLI, as it always has. A consent the portal *denied*, and a session the
compositor *took away*, do not: both are someone with the authority to say no
saying it, and sending the same input through ``/dev/uinput`` instead would
make the answer meaningless. Those two raise
:class:`~je_auto_control.linux_wayland.authorisation.WaylandAuthorisationError`
until :func:`reset_input_authorisation` is called. ``cli`` remains the way to
choose ydotool on purpose — it never asks the portal at all.

``JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`` (off by default) moves the libei
session into a helper process; see :mod:`ei_worker` for why and what it costs.

Kept separate from :mod:`_detect` so the display-server choice and
the input-pipeline choice can evolve independently.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Mapping, Optional

from je_auto_control.linux_wayland.authorisation import (
    INPUT, INPUT_RECOVERY, AuthorisationState, WaylandAuthorisationError,
    ledger,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_ENV_OVERRIDE = "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND"
_VALID = frozenset({"auto", "libei", "cli"})

#: Opt-in switch for the helper-process libei session. Off unless set.
WORKER_ENV = "JE_AUTOCONTROL_WAYLAND_EI_WORKER"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def select_input_backend(environ: Optional[dict] = None) -> str:
    """Return one of ``"libei"`` or ``"cli"`` based on env + libei probe."""
    env = environ if environ is not None else os.environ
    forced = (env.get(_ENV_OVERRIDE) or "auto").strip().lower()
    if forced not in _VALID:
        forced = "auto"
    if forced == "cli":
        return "cli"
    libei_available = _libei_loadable()
    if forced == "libei":
        if not libei_available:
            raise RuntimeError(
                "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei but libei is "
                "not loadable; install libei or unset the override",
            )
        return "libei"
    return "libei" if libei_available else "cli"


def _libei_loadable() -> bool:
    try:
        from je_auto_control.linux_wayland.libei import get_default_backend
        return get_default_backend() is not None
    except (ImportError, OSError, RuntimeError):
        return False


def worker_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """Whether the operator asked for the helper-process libei session."""
    env = environ if environ is not None else os.environ
    return (env.get(WORKER_ENV) or "").strip().lower() in _TRUTHY


def _backend_source() -> Any:
    """The module that owns the libei session: in-process, or the worker.

    Both expose ``connected_backend`` and ``last_probe_error``, so the rest of
    this module does not care which one it is talking to.
    """
    if worker_enabled():
        from je_auto_control.linux_wayland import ei_client
        return ei_client
    from je_auto_control.linux_wayland import libei
    return libei


def active_backend():
    """Return a connected libei backend, or None to use the ydotool CLI.

    The single entry point ``keyboard`` and ``mouse`` use. It lives here
    rather than in :mod:`libei` so the dependency runs one way — this module
    decides which input path is wanted, :mod:`libei` only knows how to bring
    one up. None is the answer on any host where libei is absent, there is no
    portal to ask, or the handshake does not complete.

    :raises WaylandAuthorisationError: the portal denied the request, or the
        compositor revoked a live session. Not turned into None on purpose —
        see the module docstring.
    """
    try:
        if select_input_backend() != "libei":
            return None
        source = _backend_source()
    except (ImportError, OSError, RuntimeError):
        return None
    record = ledger.get(INPUT)
    if record.blocks_fallback:
        raise WaylandAuthorisationError(record, INPUT_RECOVERY)
    if record.state in _UNASKED:
        # Visible to a diagnostics screen on another thread for as long as
        # the consent dialog is up, which can be most of a minute.
        ledger.transition(INPUT, AuthorisationState.REQUESTING,
                          "waiting for the desktop to answer")
    try:
        backend = source.connected_backend()
        failure = source.last_probe_error()
    except (ImportError, OSError, RuntimeError) as error:
        _move_to(AuthorisationState.FAILED, repr(error))
        return None
    _report_probe(backend, failure)
    return backend


#: States from which the next input action asks the desktop again.
_UNASKED = frozenset({AuthorisationState.NOT_REQUESTED,
                      AuthorisationState.CLOSED})


def _report_probe(backend: Any, failure: Optional[BaseException]) -> None:
    """Write the probe's outcome into the ledger; raise if it was a refusal."""
    if backend is not None:
        _move_to(AuthorisationState.GRANTED, "a live libei session")
        return
    if failure is None:
        _move_to(AuthorisationState.FAILED, "libei did not come up")
        return
    if getattr(failure, "declined", False):
        state = AuthorisationState.DECLINED
    elif getattr(failure, "outcome", None) == "timeout":
        state = AuthorisationState.TIMED_OUT
    else:
        state = AuthorisationState.FAILED
    if _move_to(state, str(failure)):
        autocontrol_logger.warning(
            "Wayland input: libei session not available (%s): %s",
            state.value, failure)
    ledger.require_usable(INPUT, INPUT_RECOVERY)


def _move_to(state: AuthorisationState, detail: str) -> bool:
    """Record ``state`` for input; False when it was already there."""
    if ledger.get(INPUT).state is state:
        return False
    ledger.transition(INPUT, state, detail)
    return True


def emitted(backend, send) -> bool:
    """Run one emission on ``backend``; False means the CLI has to take it.

    A backend that finished its handshake can still refuse a single
    emission: the compositor pauses a device, or a move lands outside every
    region. :mod:`libei` is documented as the fast path and never the only
    one, so such a refusal falls through to the ``ydotool`` / ``wtype`` shims
    here rather than reaching the caller — and if those are missing too,
    *they* raise. Nothing is swallowed; the failure just changes hands.

    A *revoked* session is the exception. The compositor ended it, so the
    emission is refused outright and so is every later one, until
    :func:`reset_input_authorisation`.
    """
    from je_auto_control.linux_wayland.libei import (
        LibeiSessionRevoked, LibeiUnavailable,
    )
    try:
        send(backend)
    except LibeiSessionRevoked as error:
        record = ledger.transition(INPUT, AuthorisationState.REVOKED,
                                   str(error))
        autocontrol_logger.warning("Wayland input: session revoked: %s", error)
        raise WaylandAuthorisationError(record, INPUT_RECOVERY) from error
    except LibeiUnavailable:
        return False
    return True


def _drop_sessions() -> None:
    """Disconnect whichever libei sessions this process has brought up."""
    for name in ("libei", "ei_client"):
        module = sys.modules.get(f"je_auto_control.linux_wayland.{name}")
        if module is not None:
            module.reset_default_backend()


def close_input_session() -> None:
    """End the libei session now, which is what revokes the portal grant.

    The next input action asks the portal again. Recorded as ``closed`` so a
    diagnosis can tell "we ended it" from "it was taken away".
    """
    _drop_sessions()
    ledger.transition(INPUT, AuthorisationState.CLOSED,
                      "closed by this process")


def reset_input_authorisation() -> None:
    """Forget a refused or revoked input session so it can be asked again.

    Nothing is requested here: the consent dialog appears on the next input
    action, not on this call.
    """
    _drop_sessions()
    ledger.reset(INPUT)


__all__ = ["WORKER_ENV", "active_backend", "close_input_session", "emitted",
           "reset_input_authorisation", "select_input_backend",
           "worker_enabled"]
