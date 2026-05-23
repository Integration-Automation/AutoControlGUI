"""Headless tests for the host-side connection approval callback."""
import threading
import time

import pytest

from je_auto_control.utils.remote_desktop.host import (
    PendingViewer, RemoteDesktopHost,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError,
)
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg() -> bytes:
    from io import BytesIO
    from PIL import Image
    img = Image.new("RGB", (32, 24), color=(100, 100, 100))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes():
    return _make_jpeg()


def test_approval_callback_runs_and_admits(jpeg_bytes):
    captured = []

    def approve(pending: PendingViewer) -> bool:
        captured.append(pending)
        return True

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_pending_viewer=approve,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
        viewer.connect(timeout=5.0)
        try:
            # The callback was invoked exactly once with the right pending viewer.
            deadline = time.monotonic() + 2.0
            while not captured and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(captured) == 1
            assert captured[0].host_id == host.host_id
            assert captured[0].transport == "tcp"
            # And the viewer was actually admitted (it stays connected).
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_approval_callback_rejection_disconnects(jpeg_bytes):
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_pending_viewer=lambda _pending: False,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        with pytest.raises((AuthenticationError, ConnectionError, OSError)):
            viewer.connect(timeout=3.0)
        # No client should have stuck around past the rejection.
        deadline = time.monotonic() + 1.0
        while (host.connected_clients > 0
               and time.monotonic() < deadline):
            time.sleep(0.05)
        assert host.connected_clients == 0
    finally:
        host.stop(timeout=1.0)


def test_approval_callback_exception_is_treated_as_rejection(jpeg_bytes):
    def boom(_pending):
        raise RuntimeError("operator missing")

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_pending_viewer=boom,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        with pytest.raises((AuthenticationError, ConnectionError, OSError)):
            viewer.connect(timeout=3.0)
    finally:
        host.stop(timeout=1.0)


def test_approval_callback_can_return_truthy_non_bool(jpeg_bytes):
    """Anything truthy is treated as admit; falsy as reject."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_pending_viewer=lambda _pending: "admit",  # truthy string
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
        viewer.connect(timeout=5.0)
        try:
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_default_callback_admits_everyone(jpeg_bytes):
    """Backward compatibility: no callback means admit (existing behaviour)."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
        viewer.connect(timeout=5.0)
        try:
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_pending_viewer_dataclass_frozen():
    pv = PendingViewer(
        address=("127.0.0.1", 1234), host_id="123456789", transport="tcp",
    )
    with pytest.raises((TypeError, AttributeError)):
        pv.transport = "ws"  # type: ignore[misc]


def test_ws_host_reports_transport_ws(jpeg_bytes):
    """The WS subclass labels itself ``ws`` in the pending viewer."""
    from je_auto_control.utils.remote_desktop.ws_host import (
        WebSocketDesktopHost,
    )
    from je_auto_control.utils.remote_desktop.ws_viewer import (
        WebSocketDesktopViewer,
    )

    captured = []
    host = WebSocketDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_pending_viewer=lambda pending: captured.append(pending) or True,
    )
    host.start()
    try:
        viewer = WebSocketDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            deadline = time.monotonic() + 2.0
            while not captured and time.monotonic() < deadline:
                time.sleep(0.05)
            assert captured and captured[0].transport == "ws"
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_view_only_permission_drops_input(jpeg_bytes):
    """Phase 5.3: view_only callback → host ignores INPUT messages."""
    captured = []
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        input_dispatcher=captured.append,
        on_pending_viewer=lambda _pending: "view_only",
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
        viewer.connect(timeout=5.0)
        try:
            viewer.send_input({"action": "mouse_move", "x": 1, "y": 2})
            # Give the host a moment to receive (and drop) the message.
            time.sleep(0.3)
            assert captured == []
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_full_permission_passes_input_through(jpeg_bytes):
    """Returning ``"full"`` from the callback admits + accepts input."""
    captured = []
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        input_dispatcher=captured.append,
        on_pending_viewer=lambda _pending: "full",
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
        viewer.connect(timeout=5.0)
        try:
            viewer.send_input({"action": "mouse_move", "x": 9, "y": 8})
            deadline = time.monotonic() + 2.0
            while not captured and time.monotonic() < deadline:
                time.sleep(0.05)
            assert any(c.get("action") == "mouse_move" for c in captured)
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_concurrent_clients_each_trigger_callback(jpeg_bytes):
    """Each viewer should produce a separate pending-viewer event."""
    seen = []
    lock = threading.Lock()

    def approve(pending: PendingViewer) -> bool:
        with lock:
            seen.append(pending)
        return True

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_pending_viewer=approve,
    )
    host.start()
    viewers = []
    try:
        for _ in range(3):
            v = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
            v.connect(timeout=5.0)
            viewers.append(v)
        # Allow accept-loop to drain.
        deadline = time.monotonic() + 2.0
        while len(seen) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(seen) == 3
    finally:
        for v in viewers:
            try:
                v.disconnect(timeout=1.0)
            except OSError:
                pass
        host.stop(timeout=1.0)
