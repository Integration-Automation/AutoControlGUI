"""Multi round-trip requests (MCP 2026-07-28): asking the client without calling it.

A stateless server cannot send ``elicitation/create`` and wait for the reply.
It answers the call itself with ``resultType: "input_required"``, the question
in ``inputRequests`` and its own context in ``requestState``; the client asks
the user and retries the call with the answer in ``inputResponses`` and the
state echoed back. Nothing is kept between the two requests except a record
that a state was used.

The state passes through the client, so the specification makes it
attacker-controlled input. Here it is signed with HMAC-SHA256 under a key
that exists only in this process, names the method, the tool and a digest of
the arguments, expires after :data:`STATE_TTL_S`, and is accepted once: a
retry whose state fails any of that is refused, and a confirmed destructive
call cannot be replayed with the same answer.
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any, Callable, Dict, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.mcp_server._protocol import _MCPError

#: How long a client has to answer a confirmation prompt.
STATE_TTL_S = 300
#: The ``inputRequests`` key of the destructive-tool confirmation.
CONFIRM_KEY = "confirm"
#: States remembered as used; older ones have expired long before this fills.
_MAX_REDEEMED = 4096


class AnsweredByGate(AutoControlException):
    """A gate answered the ``tools/call`` itself, before the tool ran.

    ``result`` is the whole result: an ``input_required`` prompt, or a tool
    execution error saying why the call did not run.
    """

    def __init__(self, result: Dict[str, Any]) -> None:
        super().__init__("answered by a gate")
        self.result = result


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _digest(arguments: Dict[str, Any]) -> str:
    """A stable digest of the arguments a state was issued for."""
    canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RequestStateSigner:
    """Issue and redeem the ``requestState`` of multi round-trip requests.

    Thread-safe. ``redeem`` accepts a state at most once.
    """

    def __init__(self, key: Optional[bytes] = None, ttl_s: float = STATE_TTL_S,
                 clock: Callable[[], float] = time.time) -> None:
        self._key = key if key is not None else secrets.token_bytes(32)
        self._ttl_s = float(ttl_s)
        self._clock = clock
        self._redeemed: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _mac(self, payload: str) -> str:
        return _b64(hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).digest())

    def issue(self, method: str, name: str, arguments: Dict[str, Any]) -> str:
        """A signed state for this exact method, name and arguments."""
        claims = {"m": method, "n": name, "a": _digest(arguments),
                  "exp": self._clock() + self._ttl_s, "id": secrets.token_hex(8)}
        payload = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        return f"{payload}.{self._mac(payload)}"

    def redeem(self, state: Any, method: str, name: str,
               arguments: Dict[str, Any]) -> bool:
        """True, once, for an intact unexpired state issued for this very call."""
        claims = self._verified_claims(state)
        if claims is None:
            return False
        now = self._clock()
        if (claims.get("m"), claims.get("n"), claims.get("a")) != (method, name, _digest(arguments)):
            return False
        expires = claims.get("exp")
        if not isinstance(expires, (int, float)) or expires <= now:
            return False
        with self._lock:
            self._redeemed = {key: exp for key, exp in self._redeemed.items() if exp > now}
            if state in self._redeemed or len(self._redeemed) >= _MAX_REDEEMED:
                return False
            self._redeemed[state] = float(expires)
        return True

    def _verified_claims(self, state: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(state, str) or state.count(".") != 1:
            return None
        payload, mac = state.split(".")
        if not hmac.compare_digest(mac.encode("ascii", "replace"),
                                   self._mac(payload).encode("ascii")):
            return None
        try:
            claims = json.loads(_unb64(payload))
        except ValueError:
            return None
        return claims if isinstance(claims, dict) else None


def _confirmation_prompt(signer: RequestStateSigner, name: str,
                         arguments: Dict[str, Any]) -> Dict[str, Any]:
    """The ``input_required`` result that asks the user to confirm ``name``."""
    question = {
        "method": "elicitation/create",
        "params": {
            "mode": "form",
            "message": f"AutoControl is about to run a destructive tool '{name}'. Continue?",
            "requestedSchema": {"type": "object", "properties": {}},
        },
    }
    return {
        "resultType": "input_required",
        "inputRequests": {CONFIRM_KEY: question},
        "requestState": signer.issue("tools/call", name, arguments),
    }


def require_confirmation(signer: RequestStateSigner, name: str, arguments: Dict[str, Any],
                         input_responses: Optional[Dict[str, Any]],
                         request_state: Optional[str]) -> None:
    """Return when this call carries the user's acceptance; raise otherwise.

    A first call, or a retry without an answer, is answered with the prompt
    (:class:`AnsweredByGate`); a declined or cancelled prompt with a tool
    execution error the model can read. A state that fails verification is a
    ``-32602`` protocol error.
    """
    if request_state is None:
        raise AnsweredByGate(_confirmation_prompt(signer, name, arguments))
    if not signer.redeem(request_state, "tools/call", name, arguments):
        raise _MCPError(-32602, "Invalid params: requestState is not valid for this call")
    answer = (input_responses or {}).get(CONFIRM_KEY)
    action = answer.get("action") if isinstance(answer, dict) else None
    if action is None:
        raise AnsweredByGate(_confirmation_prompt(signer, name, arguments))
    if action != "accept":
        raise AnsweredByGate({
            "content": [{"type": "text", "text": f"User declined to run {name}: action={action!r}"}],
            "isError": True,
        })
