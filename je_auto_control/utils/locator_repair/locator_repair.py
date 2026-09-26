"""Turn a successful runtime heal into a durable, review-gated locator fix.

The self-healing locator finds an element at a new place at runtime and logs the
heal — but the *corrected* location is then thrown away, so the next run heals
again from scratch. ``RepairStore`` closes that loop: it records the corrected
locator (coordinates / VLM description / method) from a heal, **auto-applies** it
when confidence is high enough, otherwise queues it as a *pending suggestion* for
review. A later run reads the learned fix via :meth:`RepairStore.resolved`.

JSON-backed via the shared ``json_store`` helper; pure standard library; imports
no ``PySide6``. Confidence/threshold are explicit, so behavior is deterministic
and fully unit-testable.
"""
import functools
import secrets
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

STATUS_PENDING = "pending"
STATUS_APPLIED = "applied"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
_USABLE = (STATUS_APPLIED, STATUS_APPROVED)


@dataclass
class RepairSuggestion:
    """A corrected locator derived from a heal, with a review status."""

    id: str
    key: str
    method: str
    confidence: float
    status: str
    coordinates: Optional[List[int]] = None
    description: Optional[str] = None


class RepairStore:
    """Records corrected locators; auto-applies confident ones, queues the rest."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """``db_path`` persists suggestions across runs (JSON)."""
        from je_auto_control.utils.json_store import SharedJsonDict
        # Re-read and locked per change, so a reviewer process and the
        # run recording suggestions do not overwrite each other.
        self._state = SharedJsonDict(db_path)

    def _items(self) -> List[Dict[str, Any]]:
        return _rows(self._state.read())

    def record(self, key: str, *, method: str,
               coordinates: Optional[List[int]] = None,
               description: Optional[str] = None, confidence: float = 1.0,
               auto_threshold: float = 0.9) -> RepairSuggestion:
        """Record a corrected locator; auto-apply if ``confidence`` clears bar."""
        # float(): "0.95" from an action file raised TypeError comparing.
        confidence, auto_threshold = float(confidence), float(auto_threshold)
        status = STATUS_APPLIED if confidence >= auto_threshold \
            else STATUS_PENDING
        suggestion = RepairSuggestion(
            id=secrets.token_hex(6), key=key, method=method,
            confidence=float(confidence), status=status,
            coordinates=list(coordinates) if coordinates else None,
            description=description)
        row = asdict(suggestion)
        self._state.update(lambda data: _writable_rows(data).append(row))
        return suggestion

    def _set_status(self, suggestion_id: str, new_status: str) -> bool:
        def set_status(data: Dict[str, Any]) -> bool:
            for item in _rows(data):
                if item.get("id") == suggestion_id and item.get("status") == STATUS_PENDING:
                    item["status"] = new_status
                    return True
            return False
        return self._state.update(set_status)

    def approve(self, suggestion_id: str) -> bool:
        """Approve a pending suggestion (makes it usable by ``resolved``)."""
        return self._set_status(suggestion_id, STATUS_APPROVED)

    def reject(self, suggestion_id: str) -> bool:
        """Reject a pending suggestion."""
        return self._set_status(suggestion_id, STATUS_REJECTED)

    def pending(self) -> List[Dict[str, Any]]:
        """Return suggestions awaiting review."""
        return [dict(i) for i in self._items() if i.get("status") == STATUS_PENDING]

    def resolved(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the latest applied/approved corrected locator for ``key``."""
        for item in reversed(self._items()):
            if item.get("key") == key and item.get("status") in _USABLE:
                return {"method": item.get("method"),
                        "coordinates": item.get("coordinates"),
                        "description": item.get("description")}
        return None


def _rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The suggestion rows that are objects; a hand-edited file raised ``KeyError`` / ``AttributeError``."""
    rows = data.get("suggestions")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _writable_rows(data: Dict[str, Any]) -> List[Any]:
    """``data["suggestions"]`` as a list to append to, replacing anything else there."""
    if not isinstance(data.get("suggestions"), list):
        data["suggestions"] = []
    return data["suggestions"]


@functools.lru_cache(maxsize=1)
def _process_store() -> RepairStore:
    return RepairStore(None)


def repair_store(db: Optional[str] = None) -> RepairStore:
    """The store saved in ``db`` or, without ``db``, the one this process shares.

    The repair commands built a fresh in-memory store per call, so without a
    ``db`` a suggestion from ``AC_repair_record`` was unknown to
    ``AC_repair_resolved`` / ``AC_repair_pending`` / ``AC_repair_approve``.
    """
    return RepairStore(db) if db else _process_store()


def repair_from_heal(heal_event: Any, key: str, *, store: RepairStore,
                     confidence: float = 1.0,
                     auto_threshold: float = 0.9) -> RepairSuggestion:
    """Record a repair from a ``HealEvent`` (object or dict) for ``key``."""
    def _field(name: str) -> Any:
        if isinstance(heal_event, dict):
            return heal_event.get(name)
        return getattr(heal_event, name, None)

    return store.record(
        key, method=str(_field("method") or "unknown"),
        coordinates=_field("coordinates"), description=_field("description"),
        confidence=confidence, auto_threshold=auto_threshold)
