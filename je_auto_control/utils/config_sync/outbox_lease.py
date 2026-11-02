"""Shared due-time checks for durable edit and peer-control leases."""
from typing import cast


def due(row: tuple[object, ...], now: float) -> bool:
    """Admit due work after lease expiry or clock rollback; terminal work remains unclaimable."""
    status, next_attempt, last_attempt, owner, lease_until = row
    if status not in {"pending", "offline", "sending"}:
        return False
    if cast(float, last_attempt) <= now:
        if owner and cast(float, lease_until) > now:
            return False
        if cast(float, next_attempt) > now:
            return False
    return True
