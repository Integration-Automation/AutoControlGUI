"""Maker-checker approval gate for high-risk automation actions.

Some automation steps (deleting records, sending money, deploying) should not
fire on one person's say-so. This implements a *segregation of duties* gate: a
**maker** files a request and receives a token; a **checker** — who must be a
different principal — approves or rejects it; the action proceeds only once
``is_approved`` is true. State is an optional JSON file so the maker and checker
can run as separate processes (CI dispatcher and a human approver).

Pure standard library; imports no ``PySide6``. Tokens use :mod:`secrets`.
"""
import secrets
import time
from typing import Dict, List, Optional

from je_auto_control.utils.json_store import read_json_dict, write_json_dict

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class ApprovalGate:
    """A maker-checker approval registry backed by an optional JSON file."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Open the gate; ``db_path`` persists state across processes."""
        self._path = db_path
        self._items: Dict[str, Dict[str, object]] = read_json_dict(db_path)

    def _flush(self) -> None:
        if self._path is not None:
            write_json_dict(self._path, self._items)

    def request(self, action: str, requester: str = "") -> str:
        """File an approval request for ``action``; return its token."""
        token = secrets.token_hex(8)
        self._items[token] = {
            "token": token, "action": action, "requester": requester,
            "status": STATUS_PENDING, "approver": "", "created": time.time(),
        }
        self._flush()
        return token

    def _decide(self, token: str, approver: str, status: str) -> bool:
        record = self._items.get(token)
        if record is None or record["status"] != STATUS_PENDING:
            return False
        if approver and approver == record["requester"]:
            return False  # segregation of duties: checker must differ from maker
        record["status"] = status
        record["approver"] = approver
        self._flush()
        return True

    def approve(self, token: str, approver: str) -> bool:
        """Approve ``token`` as ``approver`` (must differ from the requester)."""
        return self._decide(token, approver, STATUS_APPROVED)

    def reject(self, token: str, approver: str) -> bool:
        """Reject ``token`` as ``approver`` (must differ from the requester)."""
        return self._decide(token, approver, STATUS_REJECTED)

    def status(self, token: str) -> Optional[str]:
        """Return the status string for ``token``, or ``None`` if unknown."""
        record = self._items.get(token)
        return str(record["status"]) if record else None

    def is_approved(self, token: str) -> bool:
        """Return ``True`` only when ``token`` has been approved."""
        record = self._items.get(token)
        return record is not None and record["status"] == STATUS_APPROVED

    def get(self, token: str) -> Optional[Dict[str, object]]:
        """Return a copy of the request record for ``token``, or ``None``."""
        record = self._items.get(token)
        return dict(record) if record else None

    def pending(self) -> List[Dict[str, object]]:
        """Return copies of all requests still awaiting a decision."""
        return [dict(r) for r in self._items.values()
                if r["status"] == STATUS_PENDING]
