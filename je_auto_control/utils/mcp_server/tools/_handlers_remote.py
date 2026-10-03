"""MCP adapters for the remote desktop host and viewer.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
from typing import Any, Dict, Optional


# === Remote Desktop =========================================================

# pylint: disable=too-many-arguments  # reason: preserve existing positional API
def remote_host_start(
    token: str,
    bind: str = "127.0.0.1",
    port: int = 0,
    fps: float = 10.0,
    quality: int = 70,
    max_clients: int = 4,
    host_id: Optional[str] = None,
    *,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Start the script-default or named TCP host (or restart if one is running)."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.start_host(
        token=token,
        bind=bind,
        port=int(port),
        fps=float(fps),
        quality=int(quality),
        max_clients=int(max_clients),
        host_id=host_id,
        session_id=session_id,
    )
# pylint: enable=too-many-arguments


def remote_host_stop(timeout: float = 2.0, *, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Stop the active TCP host (no-op when nothing is running)."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.stop_host(timeout=float(timeout), session_id=session_id)


def remote_host_status(*, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Snapshot the host registry: running, port, host_id, client count."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.host_status(session_id=session_id)


def remote_viewer_connect(
    host: str,
    port: int,
    token: str,
    timeout: float = 5.0,
    expected_host_id: Optional[str] = None,
    *,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Open a viewer to a remote host and wait for the auth handshake."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.connect_viewer(
        host=host,
        port=int(port),
        token=token,
        timeout=float(timeout),
        expected_host_id=expected_host_id,
        session_id=session_id,
    )


def remote_viewer_disconnect(timeout: float = 2.0, *, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Close the active viewer (no-op when nothing is connected)."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.disconnect_viewer(timeout=float(timeout), session_id=session_id)


def remote_viewer_status(*, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the viewer registry snapshot: connected + remote host_id."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.viewer_status(session_id=session_id)


def remote_viewer_send_input(action: Dict[str, Any], *, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Forward ``action`` (mouse_move / type / etc.) through the viewer."""
    # pylint: disable=import-outside-toplevel  # reason: optional/cyclic transport boundary
    from je_auto_control.utils.remote_desktop.registry import registry
    # pylint: enable=import-outside-toplevel

    return registry.send_input(action, session_id=session_id)
