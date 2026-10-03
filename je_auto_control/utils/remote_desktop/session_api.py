"""JSON lifecycle adapters shared by executor commands and MCP tools."""

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from je_auto_control.utils.remote_desktop.sessions import (
    disconnect_session,
    get_remote_session,
    list_remote_session_events,
)


def remote_disconnect_session(session_id: str, *, owner: Optional[str] = None) -> Dict[str, Any]:
    """Close only the named owned connection; failed cleanup retains retry ownership."""
    return asdict(disconnect_session(session_id, owner=owner))


def remote_session_status(session_id: str, *, owner: Optional[str] = None) -> Dict[str, Any]:
    """Read immutable lifecycle identity without credentials or transport resources."""
    return asdict(get_remote_session(session_id, owner=owner))


def remote_session_events(*, owner: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read bounded owner-addressed lifecycle events without authorization data."""
    return [asdict(event) for event in list_remote_session_events(owner=owner)]
