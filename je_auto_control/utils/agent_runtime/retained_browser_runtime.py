"""Connect actual browser retirement to existing runtime leases and private completion bindings."""
from __future__ import annotations

from typing import Any, Callable

from je_auto_control.utils.agent_runtime.browser_retirement import retirement_proof, refuse_browser_input
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.retained_browser_target import RetainedBrowserTarget
from je_auto_control.utils.exception.exceptions import AutoControlException


def retire_target(runtime: Any, row: dict, target: Any, eligible: bool) -> None:
    """Keep only eligible actual contexts; every other target uses its established cleanup path."""
    if not eligible:
        target.cleanup()
        return
    # pylint: disable-next=protected-access  # reason: this collaborator owns runtime's retained process lifecycle
    with runtime._retained_browsers.reserve(row) as entry:
        if entry is None:
            target.cleanup()
            return
        detached = target.detach_readonly()
        if detached is None:
            target.cleanup()
            return
        channel, proof = detached
        try:
            # pylint: disable-next=protected-access  # reason: accept the actual reserved process, not a serialized handle
            runtime._retained_browsers.commit(entry, channel, proof)
        except BaseException:  # reason: failed collection transfer must leave the detached process with a real owner
            if entry.channel is not channel:
                # pylint: disable-next=protected-access  # reason: restore only if the collection never took ownership
                target._channel = channel
            raise


def require_source(runtime: Any, effect: dict) -> dict:
    """Validate live source authority and actual SDK proof before completion preview or admission."""
    # pylint: disable-next=protected-access  # reason: private effect admission owns this exact runtime collection
    pool = runtime._retained_browsers
    # pylint: disable-next=protected-access  # reason: the runtime supplies existing source/profile/principal checks
    source = runtime._retained_source(effect["id"])
    entry = pool.borrow(source)
    try:
        def check() -> None:
            # pylint: disable-next=protected-access  # reason: repeat current source authority during the owned RPC
            actual = runtime._retained_source(effect["id"])
            if pool.require(actual) is not entry:
                raise AgentTaskError("retained browser context is unavailable")
        check()
        proof = entry.channel.request("readonly_capabilities", {}, timeout=3, check=check,
                                      on_event=refuse_browser_input)
        if entry.proof is None:
            raise AgentTaskError("retained browser context is unavailable")
        retirement_proof(proof, entry.proof["context_id"])
        check()
        return source
    except BaseException:  # reason: failed/cancelled admission cannot retain an apparently reusable context
        pool.discard(effect["id"])
        raise
    finally:
        pool.release(entry)


def completion_adapter(runtime: Any, effect: dict, spec: Any,
                       current_operation: Callable[[], Any]) -> RetainedBrowserTarget:
    """Construct an inert closed borrower from private effect identity; readiness never launches a helper."""
    def current_source() -> dict:
        # pylint: disable-next=protected-access  # reason: private original-effect authority stays live on every read
        return runtime._retained_source(effect["id"])
    # pylint: disable-next=protected-access  # reason: share actual runtime-owned process lifetime
    return RetainedBrowserTarget(runtime._retained_browsers, effect, spec, current_source, current_operation)


def maintain_retained(runtime: Any) -> None:
    """Invalidate expired/changed/revoked sources; failed reaping remains tracked by the collection."""
    # pylint: disable-next=protected-access  # reason: host maintenance owns all retained process identities
    pool = runtime._retained_browsers
    for source in pool.sources():
        try:
            # pylint: disable-next=protected-access  # reason: reuse current runtime source authorization checks
            actual = runtime._retained_source(source["id"])
        except (AutoControlException, OSError, ValueError, LookupError):
            pool.discard(source["id"])
            continue
        try:
            pool.require(actual)
        except AgentTaskError:
            # Confirmed expiry removed its entry; a still-owned entry is an actual cleanup failure.
            if any(kept["id"] == source["id"] for kept in pool.sources()):
                raise
