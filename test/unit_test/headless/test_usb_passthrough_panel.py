"""Tests for the AnyDesk-style USB sharing panel + browser open helpers.

GUI widget tests need PySide6; the panel module lives under gui/ which
transitively pulls the webrtc extra, so the widget tests skip unless the
full GUI stack is importable. The pure helpers are tested regardless.
"""
import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

# Force a headless Qt platform before any QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from je_auto_control.utils.usb.passthrough import (  # noqa: E402
    AclRule, UsbAcl, UsbClientError, UsbLoopback,
)
from je_auto_control.utils.usb.passthrough.backend import (  # noqa: E402
    BackendDevice, FakeUsbBackend,
)

_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")


# ---------------------------------------------------------------------------
# Browser-tab helpers (need the gui import to succeed)
# ---------------------------------------------------------------------------

_browser = pytest.importorskip(
    "je_auto_control.gui.usb_browser_tab",
    reason="gui stack (webrtc extra) not importable",
)


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:9939", True),
    ("127.0.0.1:9939", True),
    ("localhost:9939", True),
    ("http://localhost", True),
    ("http://192.168.1.5:9939", False),
    ("https://example.com", False),
])
def test_is_loopback_target(url, expected):
    assert _browser._is_loopback_target(url) is expected


def test_open_local_descriptor_denied_without_acl_rule(monkeypatch, tmp_path):
    """With a default-deny ACL the local open fails closed."""
    import je_auto_control.utils.usb.passthrough.loopback as lb
    monkeypatch.setattr(
        lb, "default_passthrough_backend",
        lambda: FakeUsbBackend(devices=[_SAMPLE]),
    )
    # Point UsbAcl at an empty temp file so the user's real ACL is untouched.
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.acl.default_acl_path",
        lambda: tmp_path / "acl.json",
    )
    with pytest.raises(UsbClientError):
        _browser.open_local_descriptor(
            vendor_id="1050", product_id="0407", serial="ABC123",
        )


# ---------------------------------------------------------------------------
# Panel widget smoke (synchronous paths only — no worker-thread actions)
# ---------------------------------------------------------------------------

_panel_mod = pytest.importorskip(
    "je_auto_control.gui.usb_passthrough_panel",
    reason="gui stack (webrtc extra) not importable",
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _make_panel(qapp, tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    backend = FakeUsbBackend(devices=[_SAMPLE])
    factory = lambda: UsbLoopback(backend=backend, acl=acl, viewer_id="test")
    panel = _panel_mod.UsbPassthroughPanel(
        acl=acl, loopback_factory=factory,
    )
    return panel, acl


def test_panel_builds_and_starts_not_sharing(qapp, tmp_path):
    panel, _acl = _make_panel(qapp, tmp_path)
    try:
        assert panel._loopback is None
    finally:
        panel.deleteLater()


def test_panel_enable_then_disable_sharing(qapp, tmp_path):
    panel, _acl = _make_panel(qapp, tmp_path)
    try:
        panel._enable_sharing()
        assert panel._loopback is not None
        panel._disable_sharing()
        assert panel._loopback is None
    finally:
        panel.deleteLater()


def test_panel_enable_is_idempotent(qapp, tmp_path):
    panel, _acl = _make_panel(qapp, tmp_path)
    try:
        panel._enable_sharing()
        first = panel._loopback
        panel._enable_sharing()  # second call must not replace the loopback
        assert panel._loopback is first
    finally:
        panel._disable_sharing()
        panel.deleteLater()


def test_panel_hotplug_toggle_starts_and_stops(qapp, tmp_path):
    panel, _acl = _make_panel(qapp, tmp_path)
    try:
        panel._auto_check.setChecked(True)
        assert panel._hotplug_timer.isActive() is True
        panel._poll_hotplug()  # must not raise even with no events
        panel._auto_check.setChecked(False)
        assert panel._hotplug_timer.isActive() is False
    finally:
        panel.deleteLater()


def test_panel_remote_source_uses_provider(qapp, tmp_path):
    """When 'Remote (WebRTC)' is selected, the panel routes to the
    injected provider's client instead of the local loopback."""
    backend = FakeUsbBackend(devices=[_SAMPLE])
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    remote = UsbLoopback(backend=backend, acl=acl, viewer_id="remote")
    panel = _panel_mod.UsbPassthroughPanel(
        acl=UsbAcl(path=tmp_path / "host_acl.json"),
        loopback_factory=lambda: UsbLoopback(
            backend=FakeUsbBackend(devices=[]), acl=acl,
        ),
        remote_client_provider=lambda: remote,
    )
    try:
        # Index 1 == "Remote (WebRTC)".
        panel._source_combo.setCurrentIndex(1)
        client = panel._active_use_client()
        assert client is remote
        assert [d["vendor_id"] for d in client.list_devices()] == ["1050"]
    finally:
        remote.close()
        panel.deleteLater()


def test_panel_remote_source_without_session_warns(qapp, tmp_path):
    panel = _panel_mod.UsbPassthroughPanel(
        acl=UsbAcl(path=tmp_path / "acl.json"),
        loopback_factory=lambda: UsbLoopback(
            backend=FakeUsbBackend(devices=[]),
            acl=UsbAcl(path=tmp_path / "acl.json"),
        ),
        remote_client_provider=lambda: None,  # no live WebRTC session
    )
    try:
        panel._source_combo.setCurrentIndex(1)
        import pytest as _pytest
        with _pytest.raises(RuntimeError):
            panel._active_use_client()
    finally:
        panel.deleteLater()


def test_panel_local_source_is_default(qapp, tmp_path):
    panel, _acl = _make_panel(qapp, tmp_path)
    try:
        assert panel._source_combo.currentIndex() == 0
        panel._enable_sharing()
        assert panel._active_use_client() is panel._loopback
    finally:
        panel._disable_sharing()
        panel.deleteLater()


def test_panel_export_import_acl_round_trip(qapp, tmp_path):
    panel, acl = _make_panel(qapp, tmp_path)
    try:
        acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
        out = tmp_path / "exp.json"
        from je_auto_control.utils.usb.passthrough import (
            export_acl_to_file, import_acl_from_file,
        )
        export_acl_to_file(acl, out)
        fresh = UsbAcl(path=tmp_path / "fresh.json")
        assert import_acl_from_file(fresh, out) == 1
    finally:
        panel.deleteLater()
