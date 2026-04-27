"""Tests for the USB passthrough ACL prompt dialog (round 44)."""
import os
import threading

import pytest

# Force offscreen so the dialog never tries to draw on a real display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pyside = pytest.importorskip("PySide6.QtWidgets")
# gui/__init__.py eagerly loads main_window → webrtc_panel → aiortc.
# The dialog itself only needs Qt, but we have to satisfy the chain
# to import anything from je_auto_control.gui.
pytest.importorskip("av")
pytest.importorskip("aiortc")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from je_auto_control.gui.usb_passthrough_prompt import (  # noqa: E402
    PromptBridge, UsbPassthroughPromptDialog, attach_prompt_to_session,
)
from je_auto_control.utils.usb.passthrough import (  # noqa: E402
    UsbAcl, UsbPassthroughSession,
)
from je_auto_control.utils.usb.passthrough.backend import (  # noqa: E402
    BackendDevice, FakeUsbBackend,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Dialog widget unit tests
# ---------------------------------------------------------------------------


def test_dialog_displays_supplied_descriptors(qapp):
    dialog = UsbPassthroughPromptDialog(
        vendor_id="1050", product_id="0407",
        serial="ABC123", viewer_id="vw-test",
    )
    # We don't introspect the rendered text labels (Qt internals); just
    # assert the constructor stored what we passed for the bridge to
    # later read back if needed.
    assert dialog._vendor_id == "1050"
    assert dialog._product_id == "0407"
    assert dialog._serial == "ABC123"
    assert dialog._viewer_id == "vw-test"
    assert dialog.remember is False


def test_dialog_remember_reflects_checkbox(qapp):
    dialog = UsbPassthroughPromptDialog(
        vendor_id="1050", product_id="0407",
        serial=None, viewer_id=None,
    )
    dialog._remember_check.setChecked(True)
    assert dialog.remember is True


# ---------------------------------------------------------------------------
# PromptBridge — worker → GUI → worker round-trip
# ---------------------------------------------------------------------------


def _drive_dialog_when_visible(action: str) -> None:
    """Schedule a one-shot Qt timer that finds the modal dialog and
    presses Allow / Deny / cancel on it.
    """
    def attempt():
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, UsbPassthroughPromptDialog) and widget.isVisible():
                if action == "allow":
                    widget.accept()
                elif action == "deny":
                    widget.reject()
                elif action == "remember-allow":
                    widget._remember_check.setChecked(True)
                    widget.accept()
                else:
                    widget.reject()
                return
        # Try again shortly if the dialog hasn't appeared yet.
        QTimer.singleShot(20, attempt)
    QTimer.singleShot(50, attempt)


def test_bridge_returns_true_on_allow(qapp):
    bridge = PromptBridge()
    _drive_dialog_when_visible("allow")
    result = bridge.decide(
        vendor_id="1050", product_id="0407", serial=None,
        viewer_id="vw", wait_timeout_s=3.0,
    )
    assert result is True


def test_bridge_returns_false_on_deny(qapp):
    bridge = PromptBridge()
    _drive_dialog_when_visible("deny")
    result = bridge.decide(
        vendor_id="1050", product_id="0407", serial=None,
        viewer_id="vw", wait_timeout_s=3.0,
    )
    assert result is False


def test_bridge_remember_persists_acl_rule(qapp, tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    bridge = PromptBridge(acl=acl)
    _drive_dialog_when_visible("remember-allow")
    result = bridge.decide(
        vendor_id="1050", product_id="0407", serial=None,
        viewer_id="vw", wait_timeout_s=3.0,
    )
    assert result is True
    rules = acl.list_rules()
    assert len(rules) == 1
    assert rules[0].vendor_id == "1050"
    assert rules[0].allow is True
    assert rules[0].prompt_on_open is False


def test_bridge_remember_no_acl_does_not_crash(qapp):
    """``acl=None`` is allowed — remember just becomes a no-op write."""
    bridge = PromptBridge()  # no acl
    _drive_dialog_when_visible("remember-allow")
    result = bridge.decide(
        vendor_id="1050", product_id="0407", serial=None,
        viewer_id="vw", wait_timeout_s=3.0,
    )
    assert result is True


def test_bridge_timeout_returns_false(qapp):
    """If the operator never responds within the timeout, decide() must
    fail closed (deny)."""
    bridge = PromptBridge()
    # Don't schedule any timer — the dialog will sit there until timeout.
    result = bridge.decide(
        vendor_id="1050", product_id="0407", serial=None,
        viewer_id="vw", wait_timeout_s=0.3,
    )
    assert result is False
    # Drain Qt events so the abandoned dialog doesn't leak into the next test.
    qapp.processEvents()


# ---------------------------------------------------------------------------
# Session integration via attach_prompt_to_session
# ---------------------------------------------------------------------------


def test_attach_prompt_wires_callback_into_session(qapp, tmp_path):
    backend = FakeUsbBackend(devices=[
        BackendDevice(vendor_id="1050", product_id="0407", serial="ABC"),
    ])
    acl = UsbAcl(path=tmp_path / "acl.json")
    from je_auto_control.utils.usb.passthrough.acl import AclRule
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         allow=True, prompt_on_open=True))

    session = UsbPassthroughSession(backend, acl=acl)
    bridge = attach_prompt_to_session(session, acl=acl)
    assert isinstance(bridge, PromptBridge)
    # The session's callback should now point at the bridge's decide.
    assert session._prompt_callback is bridge.decide

    # End-to-end: pre-arm an "allow" click, drive the OPEN frame from a
    # background thread (so the prompt is truly cross-thread), and check
    # the OPEN succeeds.
    import json
    from je_auto_control.utils.usb.passthrough import Frame, Opcode
    open_frame = Frame(
        op=Opcode.OPEN,
        payload=json.dumps({
            "vendor_id": "1050", "product_id": "0407", "serial": "ABC",
        }).encode("utf-8"),
    )

    captured: dict = {}

    def background():
        replies = session.handle_frame(open_frame)
        captured["body"] = json.loads(replies[0].payload.decode("utf-8"))

    _drive_dialog_when_visible("allow")
    worker = threading.Thread(target=background)
    worker.start()
    # Pump Qt events while the worker thread waits for the prompt.
    deadline = 3.0
    interval = 0.02
    waited = 0.0
    while worker.is_alive() and waited < deadline:
        qapp.processEvents()
        worker.join(interval)
        waited += interval
    assert not worker.is_alive(), "OPEN never returned"
    assert captured["body"]["ok"] is True


def test_attach_prompt_requires_qapplication(monkeypatch):
    """Calling attach_prompt_to_session before QApplication is up is
    a programming error, not silent failure."""
    from PySide6.QtWidgets import QApplication as RealApp
    monkeypatch.setattr(RealApp, "instance", staticmethod(lambda: None))
    backend = FakeUsbBackend()
    session = UsbPassthroughSession(backend)
    with pytest.raises(RuntimeError) as exc_info:
        attach_prompt_to_session(session)
    assert "QApplication" in str(exc_info.value)
    _ = QDialog  # silence unused import warning if Qt eagerly trims
