"""Maker-checker approval gate for high-risk automation actions.

Some automation steps (deleting records, sending money, deploying) should not
fire on one person's say-so. This implements a *segregation of duties* gate: a
**maker** files a request and receives a token; a **checker** — who must be a
different principal — approves or rejects it; the action proceeds only once
``is_approved`` is true. State is an optional JSON file so the maker and checker
can run as separate processes (CI dispatcher and a human approver).

Pure standard library; imports no ``PySide6``. Tokens use :mod:`secrets`.
"""
import functools
import secrets
import time
import unicodedata
from typing import Dict, List, Optional

from je_auto_control.utils.json_store import SharedJsonDict

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"



def _principal(user: object) -> str:
    """Compare user ids as one person: "Alice" approving "alice" is self-approval."""
    return unicodedata.normalize("NFKC", str(user or "")).strip().casefold()

class ApprovalGate:
    """A maker-checker approval registry backed by an optional JSON file.

    With a file, every decision re-reads it under a lock, so a request can be
    decided once even when the maker and several checkers are separate
    processes.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Open the gate; ``db_path`` persists state across processes."""
        self._state = SharedJsonDict(db_path)

    def request(self, action: str, requester: str = "") -> str:
        """File an approval request for ``action``; return its token."""
        token = secrets.token_hex(8)
        record = {
            "token": token, "action": action, "requester": requester,
            "status": STATUS_PENDING, "approver": "", "created": time.time(),
        }
        self._state.update(lambda items: items.__setitem__(token, record))
        return token

    def _decide(self, token: str, approver: str, status: str) -> bool:
        checker = _principal(approver)

        def decide(items: Dict[str, Dict[str, object]]) -> bool:
            record = items.get(token)
            if record is None or record["status"] != STATUS_PENDING:
                return False
            # Segregation of duties: a named checker who is not the maker. An
            # empty approver skipped the check (anonymous approved anonymous).
            if not checker or checker == _principal(record["requester"]):
                return False
            record["status"] = status
            record["approver"] = approver
            return True
        return self._state.update(decide)

    def approve(self, token: str, approver: str) -> bool:
        """Approve ``token`` as ``approver`` (must differ from the requester)."""
        return self._decide(token, approver, STATUS_APPROVED)

    def reject(self, token: str, approver: str) -> bool:
        """Reject ``token`` as ``approver`` (must differ from the requester)."""
        return self._decide(token, approver, STATUS_REJECTED)

    def status(self, token: str) -> Optional[str]:
        """Return the status string for ``token``, or ``None`` if unknown."""
        record = self._state.read().get(token)
        return str(record["status"]) if record else None

    def is_approved(self, token: str) -> bool:
        """Return ``True`` only when ``token`` has been approved."""
        record = self._state.read().get(token)
        return record is not None and record["status"] == STATUS_APPROVED

    def get(self, token: str) -> Optional[Dict[str, object]]:
        """Return a copy of the request record for ``token``, or ``None``."""
        record = self._state.read().get(token)
        return dict(record) if record else None

    def pending(self) -> List[Dict[str, object]]:
        """Return copies of all requests still awaiting a decision."""
        return [dict(r) for r in self._state.read().values()
                if r["status"] == STATUS_PENDING]


@functools.lru_cache(maxsize=1)
def _process_gate() -> ApprovalGate:
    return ApprovalGate(None)


def approval_gate(db: Optional[str] = None) -> ApprovalGate:
    """The gate stored in ``db`` or, without ``db``, the one this process shares.

    The approval commands built a fresh in-memory gate per call, so without a
    ``db`` a token from ``AC_approval_request`` was unknown to
    ``AC_approval_approve`` / ``AC_approval_status``.
    """
    return ApprovalGate(db) if db else _process_gate()

