"""Audit round 3 regressions for RemoteDesktopViewer.

Covers:
* Finding 2 — connect() must close the raw socket when the WebSocket
  handshake raises WsProtocolError (a RuntimeError subclass), not leak the fd.
* Finding 5 — disconnect() called from inside a frame/error callback (i.e. on
  the receiver thread) must skip the self-join and still finish teardown.
"""
import socket
import threading

import pytest

from je_auto_control.utils.remote_desktop import viewer as viewer_module
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_protocol import WsProtocolError


def test_connect_closes_socket_on_ws_protocol_error(monkeypatch):
    """A WsProtocolError during handshake must not leak the raw socket."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    held = []

    def _accept_once() -> None:
        try:
            conn, _addr = listener.accept()
            held.append(conn)  # keep the connection open past handshake fail
        except OSError:
            pass

    threading.Thread(target=_accept_once, daemon=True).start()

    captured = {}
    real_create = socket.create_connection

    def _spy_create(address, timeout=None):
        raw = real_create(address, timeout=timeout)
        captured["sock"] = raw
        return raw

    monkeypatch.setattr(viewer_module.socket, "create_connection", _spy_create)

    class _WsFailViewer(RemoteDesktopViewer):
        def _handshake(self, channel):
            raise WsProtocolError("bad ws upgrade")

    viewer = _WsFailViewer("127.0.0.1", port, "tok")
    try:
        with pytest.raises(WsProtocolError):
            viewer.connect(timeout=2.0)
        # Pre-fix the except tuple omitted WsProtocolError, so the raw socket
        # stayed open (fileno() != -1). The fix closes it.
        raw = captured["sock"]
        assert raw.fileno() == -1
    finally:
        listener.close()
        for conn in held:
            try:
                conn.close()
            except OSError:
                pass


def test_disconnect_from_receiver_thread_completes_teardown():
    """disconnect() on the receiver thread must not raise and must tear down."""
    viewer = RemoteDesktopViewer("127.0.0.1", 1, "tok")
    viewer._channel = None  # skip channel.close()
    result = {}

    def _worker() -> None:
        viewer._connected = True
        try:
            viewer.disconnect(timeout=1.0)
            result["error"] = None
        except RuntimeError as exc:  # pre-fix: "cannot join current thread"
            result["error"] = exc

    worker = threading.Thread(target=_worker)
    # Make the running worker *be* the viewer's receiver thread.
    viewer._receiver = worker
    worker.start()
    worker.join(timeout=3.0)

    assert not worker.is_alive()
    assert result.get("error") is None
    assert viewer._receiver is None
    assert viewer.connected is False
