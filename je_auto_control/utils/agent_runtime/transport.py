"""Bounded HTTP requests; cancellation discards late inference replies before any input."""
from __future__ import annotations

import queue
import threading
import time
from contextvars import copy_context
from typing import Any, Callable, NoReturn

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError, AgentObservationStale
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint
from je_auto_control.utils.http_client.http_client import build_call, urllib_transport

_SLOTS = threading.BoundedSemaphore(4)
_CONTROL_SLOTS = threading.BoundedSemaphore(2)


def request_json(url: str, *, body: Any = None, token: str | None = None,
                 timeout: float = 30, check: Callable[[], None] = cancellation_checkpoint,
                 control: bool = False) -> dict[str, Any]:
    """Use existing egress/redirect checks and bound resource use across cancelled callers."""
    from je_auto_control.utils.agent_runtime.models import positive
    positive(timeout, "HTTP timeout", 3600)
    check()
    slots = _CONTROL_SLOTS if control else _SLOTS
    _acquire(slots, timeout if control else 0, check)
    replies: queue.Queue[Any] = queue.Queue(maxsize=1)
    context = copy_context()

    def fetch() -> None:
        try:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            if token:
                from je_auto_control.utils.agent_runtime.origin_policy import HEADER as ORIGIN_HEADER, current_origin
                if current_origin() is not None:
                    headers[ORIGIN_HEADER] = str(current_origin())
                from urllib.parse import urlparse
                from je_auto_control.utils.agent_runtime.delegation import HEADER, sign_principal
                from je_auto_control.utils.rbac.authorization import current_authorization
                identity = current_authorization()
                if identity is not None:
                    headers[HEADER] = sign_principal(identity, token, urlparse(url).path)
            from je_auto_control.utils.egress.egress_policy import get_egress_policy
            get_egress_policy().check(url)
            call = build_call(url, method="POST" if body is not None else "GET",
                              headers=headers, json_body=body, timeout=timeout)
            call["follow_redirects"] = False
            replies.put(urllib_transport(call))
        except BaseException as error:  # reason: hand controls back to the owning caller; no failure is swallowed
            replies.put(error)
        finally:
            slots.release()

    threading.Thread(target=lambda: context.run(fetch), daemon=True, name="AgentHTTP").start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check()
        try:
            reply = replies.get(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if isinstance(reply, BaseException):
            raise reply
        check()
        if not 200 <= reply.get("status", 0) < 300 or not isinstance(reply.get("json"), dict):
            _raise_reply_error(reply)
        return reply["json"]
    raise AgentTaskError("local HTTP request timed out")


def _raise_reply_error(reply: dict) -> NoReturn:
    payload = reply.get("json")
    detail = payload.get("error", "operation failed") if isinstance(payload, dict) else "invalid JSON reply"
    if isinstance(payload, dict) and payload.get("error_type") == "stale_observation":
        raise AgentObservationStale(f"local HTTP observation changed: {detail}")
    if isinstance(payload, dict) and payload.get("error_type") == "human_review":
        from je_auto_control.utils.agent_runtime.errors import AgentHumanReview
        raise AgentHumanReview(f"local HTTP human review required: {detail}")
    raise AgentTaskError(f"local HTTP operation failed ({reply.get('status', 0)}): {detail}")


def _acquire(slots: Any, timeout: float, check: Callable[[], None]) -> None:
    deadline = time.monotonic() + timeout
    while True:
        check()
        if slots.acquire(blocking=False):
            return
        if time.monotonic() >= deadline:
            raise AgentControlBusy("local HTTP request capacity is busy")
        time.sleep(0.01)
