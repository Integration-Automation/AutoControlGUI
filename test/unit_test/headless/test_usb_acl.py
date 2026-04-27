"""Tests for the USB passthrough ACL + session integration (round 41)."""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.usb.passthrough import (
    AclRule, Frame, Opcode, UsbAcl, UsbPassthroughSession,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)


_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC")


# ---------------------------------------------------------------------------
# UsbAcl unit tests
# ---------------------------------------------------------------------------


def test_default_policy_is_deny(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    verdict = acl.decide(vendor_id="1050", product_id="0407", serial="ABC")
    assert verdict == "deny"


def test_explicit_default_policy_can_allow(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json", default_policy="allow")
    verdict = acl.decide(vendor_id="1050", product_id="0407", serial=None)
    assert verdict == "allow"


def test_invalid_default_policy_raises(tmp_path):
    with pytest.raises(ValueError):
        UsbAcl(path=tmp_path / "acl.json", default_policy="maybe")


def test_allow_rule_matches_exact_vid_pid(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    assert acl.decide(vendor_id="1050", product_id="0407", serial=None) == "allow"
    # A different PID still hits the default deny.
    assert acl.decide(vendor_id="1050", product_id="9999", serial=None) == "deny"


def test_serial_wildcard_matches_anything(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         serial=None, allow=True))
    for serial in (None, "ABC", "XYZ"):
        assert acl.decide(vendor_id="1050", product_id="0407",
                          serial=serial) == "allow"


def test_serial_specific_rule_only_matches_that_serial(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         serial="MINE", allow=True))
    assert acl.decide(vendor_id="1050", product_id="0407",
                      serial="MINE") == "allow"
    # Same vid/pid but different serial → no rule match → default deny.
    assert acl.decide(vendor_id="1050", product_id="0407",
                      serial="OTHER") == "deny"


def test_first_matching_rule_wins(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=False))
    assert acl.decide(vendor_id="1050", product_id="0407", serial=None) == "allow"


def test_prompt_rule_returns_prompt(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         allow=True, prompt_on_open=True))
    assert acl.decide(vendor_id="1050", product_id="0407",
                      serial=None) == "prompt"


def test_remove_rule(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    assert acl.remove_rule(vendor_id="1050", product_id="0407",
                           serial=None) is True
    assert acl.list_rules() == []
    assert acl.remove_rule(vendor_id="1050", product_id="0407",
                           serial=None) is False


def test_save_and_reload_round_trip(tmp_path):
    path = tmp_path / "acl.json"
    a = UsbAcl(path=path, default_policy="allow")
    a.add_rule(AclRule(vendor_id="1050", product_id="0407",
                       label="YubiKey", allow=True, prompt_on_open=False))
    # Reload from disk.
    b = UsbAcl(path=path)
    assert b.default_policy == "allow"
    rules = b.list_rules()
    assert len(rules) == 1
    assert rules[0].vendor_id == "1050"
    assert rules[0].label == "YubiKey"


def test_corrupt_file_falls_back_to_default(tmp_path):
    path = tmp_path / "acl.json"
    path.write_text("not json", encoding="utf-8")
    acl = UsbAcl(path=path)
    assert acl.default_policy == "deny"
    assert acl.list_rules() == []


def test_unknown_version_is_ignored(tmp_path):
    path = tmp_path / "acl.json"
    path.write_text(json.dumps({
        "version": 99, "default": "allow", "rules": [],
    }), encoding="utf-8")
    acl = UsbAcl(path=path)
    # File rejected → in-memory default-deny stays.
    assert acl.default_policy == "deny"


# ---------------------------------------------------------------------------
# Session integration
# ---------------------------------------------------------------------------


def _open_frame() -> Frame:
    return Frame(
        op=Opcode.OPEN,
        payload=json.dumps({
            "vendor_id": "1050", "product_id": "0407", "serial": "ABC",
        }).encode("utf-8"),
    )


def _decode_opened(frame: Frame) -> dict:
    return json.loads(frame.payload.decode("utf-8"))


def test_session_with_default_deny_acl_rejects_open(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")  # default deny
    backend = FakeUsbBackend(devices=[_SAMPLE])
    session = UsbPassthroughSession(backend, acl=acl)
    reply = session.handle_frame(_open_frame())[0]
    assert reply.op == Opcode.OPENED
    body = _decode_opened(reply)
    assert body["ok"] is False
    assert "ACL" in body["error"] or "denied" in body["error"]
    assert backend.open_handle_count == 0


def test_session_with_allow_rule_lets_open_through(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    backend = FakeUsbBackend(devices=[_SAMPLE])
    session = UsbPassthroughSession(backend, acl=acl)
    reply = session.handle_frame(_open_frame())[0]
    body = _decode_opened(reply)
    assert body["ok"] is True
    assert backend.open_handle_count == 1


def test_session_prompt_calls_callback_and_honors_yes(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         allow=True, prompt_on_open=True))
    backend = FakeUsbBackend(devices=[_SAMPLE])
    callbacks: list = []

    def prompt(vid: str, pid: str, serial):
        callbacks.append((vid, pid, serial))
        return True

    session = UsbPassthroughSession(backend, acl=acl,
                                    prompt_callback=prompt)
    body = _decode_opened(session.handle_frame(_open_frame())[0])
    assert body["ok"] is True
    assert callbacks == [("1050", "0407", "ABC")]


def test_session_prompt_no_callback_means_deny(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         allow=True, prompt_on_open=True))
    backend = FakeUsbBackend(devices=[_SAMPLE])
    session = UsbPassthroughSession(backend, acl=acl)
    body = _decode_opened(session.handle_frame(_open_frame())[0])
    assert body["ok"] is False


def test_session_prompt_callback_raising_means_deny(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407",
                         allow=True, prompt_on_open=True))

    def boom(_v, _p, _s):
        raise RuntimeError("dialog crashed")

    session = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE]),
        acl=acl, prompt_callback=boom,
    )
    body = _decode_opened(session.handle_frame(_open_frame())[0])
    assert body["ok"] is False


def test_session_audit_captures_open_decisions(tmp_path):
    """Use a temp audit log path so the test doesn't pollute the user's."""
    from je_auto_control.utils.remote_desktop.audit_log import AuditLog
    audit = AuditLog(path=tmp_path / "audit.db")
    acl = UsbAcl(path=tmp_path / "acl.json")  # default deny
    session = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE]),
        acl=acl, viewer_id="vw-xyz", audit_log=audit,
    )
    session.handle_frame(_open_frame())  # → denied
    rows = audit.query()
    assert any(r["event_type"] == "usb_open_denied" for r in rows), rows
    denied = next(r for r in rows if r["event_type"] == "usb_open_denied")
    assert "1050:0407" in (denied["host_id"] or "")
    assert denied["viewer_id"] == "vw-xyz"
    audit.close()


def test_save_persists_to_disk_with_safe_mode(tmp_path):
    """File must be readable as JSON; on POSIX it should be 0600."""
    import os as _os
    path: Path = tmp_path / "acl.json"
    acl = UsbAcl(path=path)
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    if _os.name == "posix":
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600
