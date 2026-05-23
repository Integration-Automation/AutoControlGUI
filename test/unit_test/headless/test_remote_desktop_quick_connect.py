"""Headless Qt tests for the AnyDesk-style Quick Connect screen."""
import os
import time
from io import BytesIO

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PIL = pytest.importorskip("PIL.Image")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.utils.remote_desktop.registry import registry  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def reset_registry():
    registry.disconnect_viewer()
    registry.stop_host()
    yield
    registry.disconnect_viewer()
    registry.stop_host()


def _make_jpeg(width: int = 32, height: int = 24) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(0, 200, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _process_until(app: QApplication, predicate, timeout: float = 3.0,
                   interval_ms: int = 20) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(interval_ms / 1000.0)
    app.processEvents()
    return predicate()


# --- screen instantiation + hosting lifecycle ----------------------------
# (target-string parsing lives in test_remote_desktop_connect_coordinator.py)

def test_quick_connect_screen_instantiates(qapp):
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    screen = QuickConnectScreen()
    try:
        # Status badges and ID label exist and start in their idle state.
        assert screen._host_id_label.text() == "---"  # noqa: SLF001
        assert screen._host_badge.text()  # noqa: SLF001
        assert screen._viewer_badge.text()  # noqa: SLF001
    finally:
        screen.deleteLater()


def test_generate_token_fills_field(qapp):
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    screen = QuickConnectScreen()
    try:
        assert screen._host_token.text() == ""  # noqa: SLF001
        screen._generate_token()  # noqa: SLF001
        assert len(screen._host_token.text()) >= 16  # noqa: SLF001
    finally:
        screen.deleteLater()


def test_start_hosting_registers_host_and_refreshes_badge(qapp):
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    screen = QuickConnectScreen()
    try:
        screen._host_token.setText("ttt")  # noqa: SLF001
        screen._start_hosting()  # noqa: SLF001
        assert registry.host is not None
        assert registry.host.is_running
        # Badge text updated from the idle placeholder to running text.
        assert "{port}" not in screen._host_badge.text()  # noqa: SLF001
        screen._stop_hosting()  # noqa: SLF001
        assert registry.host is None
    finally:
        screen.deleteLater()


# --- end-to-end via the screen's public connect flow --------------------

def test_quick_connect_round_trips_frame_to_popup(qapp):
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

    jpeg = _make_jpeg()
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg,
    )
    host.start()
    registry._host = host  # noqa: SLF001  test-only injection
    try:
        screen = QuickConnectScreen()
        try:
            screen._connect_target.setText(  # noqa: SLF001
                f"127.0.0.1:{host.port}",
            )
            screen._connect_token.setText("t")  # noqa: SLF001
            screen._connect()  # noqa: SLF001

            assert registry.viewer is not None
            # Wait until the pop-out window receives at least one frame.
            window = screen._screen_window  # noqa: SLF001
            assert window is not None
            assert _process_until(qapp, window.display.has_image)
            screen._disconnect()  # noqa: SLF001
            assert registry.viewer is None
        finally:
            screen.deleteLater()
    finally:
        host.stop(timeout=1.0)
        registry._host = None  # noqa: SLF001


def test_publish_via_signaling_emits_host_handoff(qapp):
    """Clicking the host-handoff button forwards token + host_id."""
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    screen = QuickConnectScreen()
    try:
        screen._host_token.setText("ttt")  # noqa: SLF001
        screen._start_hosting()  # noqa: SLF001
        captured = []
        screen.webrtc_host_handoff_requested.connect(
            lambda token, host_id: captured.append((token, host_id)),
        )
        screen._on_publish_via_signaling()  # noqa: SLF001
        assert len(captured) == 1
        token, host_id = captured[0]
        assert token == "ttt"
        # host_id should be the 9-digit ID of the running TCP host.
        assert host_id and len(host_id) == 9 and host_id.isdigit()
        screen._stop_hosting()  # noqa: SLF001
    finally:
        screen.deleteLater()


def test_nine_digit_id_emits_webrtc_handoff(qapp):
    """Typing an AnyDesk-style 9-digit ID hands off to the WebRTC tab."""
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    screen = QuickConnectScreen()
    try:
        captured = []
        screen.webrtc_handoff_requested.connect(
            lambda host_id, token: captured.append((host_id, token)),
        )
        screen._connect_target.setText("123-456-789")  # noqa: SLF001
        screen._connect_token.setText("ttt")  # noqa: SLF001
        screen._connect()  # noqa: SLF001
        assert captured == [("123456789", "ttt")]
        # No TCP viewer should have been created since this is a handoff.
        assert registry.viewer is None
    finally:
        screen.deleteLater()


def test_approval_dialog_admits_when_operator_clicks_allow(qapp, monkeypatch):
    """A simulated 'Allow' click admits the incoming viewer."""
    from je_auto_control.gui.remote_desktop import connection_screen as cs_mod
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )

    # Stub the modal dialog so it answers 'Allow' without blocking.
    def fake_show_dialog(self, request):
        request.decision = "full"
        request.event.set()

    monkeypatch.setattr(
        QuickConnectScreen, "_show_approval_dialog", fake_show_dialog,
    )

    screen = QuickConnectScreen()
    try:
        screen._host_token.setText("ttt")  # noqa: SLF001
        screen._start_hosting()  # noqa: SLF001
        host = registry.host
        assert host is not None
        try:
            from je_auto_control.utils.remote_desktop.viewer import (
                RemoteDesktopViewer,
            )
            viewer = RemoteDesktopViewer(
                host="127.0.0.1", port=host.port, token="ttt",
            )
            # Run viewer.connect on a worker thread so the GUI event loop
            # can pump the queued approval signal in the meantime.
            import threading
            connect_done = threading.Event()
            connect_result = {"ok": False, "error": None}

            def attempt_connect():
                try:
                    viewer.connect(timeout=5.0)
                    connect_result["ok"] = True
                except Exception as exc:  # noqa: BLE001
                    connect_result["error"] = exc
                finally:
                    connect_done.set()

            threading.Thread(target=attempt_connect, daemon=True).start()
            assert _process_until(qapp, connect_done.is_set, timeout=6.0)
            assert connect_result["ok"], connect_result["error"]
            assert viewer.connected
            viewer.disconnect(timeout=1.0)
        finally:
            screen._stop_hosting()  # noqa: SLF001
    finally:
        screen.deleteLater()
    _ = cs_mod  # keep import for namespace stability


def test_approval_dialog_rejects_when_operator_clicks_deny(qapp, monkeypatch):
    """A simulated 'Deny' click rejects the incoming viewer."""
    from je_auto_control.gui.remote_desktop.connection_screen import (
        QuickConnectScreen,
    )
    from je_auto_control.utils.remote_desktop.protocol import (
        AuthenticationError,
    )
    from je_auto_control.utils.remote_desktop.viewer import (
        RemoteDesktopViewer,
    )

    def fake_show_dialog(self, request):
        request.decision = "denied"
        request.event.set()

    monkeypatch.setattr(
        QuickConnectScreen, "_show_approval_dialog", fake_show_dialog,
    )

    screen = QuickConnectScreen()
    try:
        screen._host_token.setText("ttt")  # noqa: SLF001
        screen._start_hosting()  # noqa: SLF001
        host = registry.host
        assert host is not None
        try:
            viewer = RemoteDesktopViewer(
                host="127.0.0.1", port=host.port, token="ttt",
            )
            import threading
            done = threading.Event()
            captured = {}

            def attempt():
                try:
                    viewer.connect(timeout=5.0)
                except (AuthenticationError, OSError, ConnectionError) as exc:
                    captured["error"] = exc
                finally:
                    done.set()

            threading.Thread(target=attempt, daemon=True).start()
            assert _process_until(qapp, done.is_set, timeout=6.0)
            assert "error" in captured
        finally:
            screen._stop_hosting()  # noqa: SLF001
    finally:
        screen.deleteLater()


def test_recent_connections_populated_after_connect(qapp, tmp_path,
                                                    monkeypatch):
    """A successful connect appends the target to the AddressBook."""
    from je_auto_control.utils.remote_desktop import address_book as ab_mod
    from je_auto_control.gui.remote_desktop import connection_screen as cs_mod
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

    # Redirect the default address book onto a per-test file so we do not
    # pollute the user's real ~/.je_auto_control/address_book.json.
    book = ab_mod.AddressBook(tmp_path / "book.json")
    monkeypatch.setattr(cs_mod, "default_address_book", lambda: book)
    # Reset the module-level singleton so default_address_book is re-read.
    monkeypatch.setattr(ab_mod, "_default_address_book", book)

    jpeg = _make_jpeg()
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg,
    )
    host.start()
    registry._host = host  # noqa: SLF001
    try:
        screen = cs_mod.QuickConnectScreen()
        try:
            screen._connect_target.setText(  # noqa: SLF001
                f"127.0.0.1:{host.port}",
            )
            screen._connect_token.setText("t")  # noqa: SLF001
            screen._connect()  # noqa: SLF001

            entries = book.list_entries()
            expected_url = f"tcp://127.0.0.1:{host.port}"
            assert any(e["host_id"] == expected_url for e in entries)
            assert screen._recent.count() >= 1  # noqa: SLF001
            screen._disconnect()  # noqa: SLF001
        finally:
            screen.deleteLater()
    finally:
        host.stop(timeout=1.0)
        registry._host = None  # noqa: SLF001
