"""The USB ACL and its signature are one file, changed under one lock.

The ACL was two files: the JSON and a ``.sig`` holding its HMAC. Each was
written on its own, and the lock around a change belonged to the instance, so
a second instance -- the GUI next to a host session -- or a second process
could read the new data against the old signature (a "signature mismatch" on a
file nobody tampered with, which fails closed to deny-all) or re-read the file
between another writer's read and write and save over its rule.

Temp files only; the child process is this interpreter running a few lines
against the same temp file.
"""
import hashlib
import hmac
import json
import logging
import subprocess
import sys
import threading

import pytest

from je_auto_control.utils.json_store import json_store
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.acl import AclRule, UsbAcl, UsbAclBusyError

_WAIT = 60.0
_PER_WRITER = 20


def _rule(index, vendor="1050"):
    return AclRule(vendor_id=vendor, product_id=f"{index:04x}", allow=True)


def _products(acl):
    return sorted((rule.vendor_id, rule.product_id) for rule in acl.list_rules())


def _legacy_layout(directory, payload, key=b"k" * 32, signed=True):
    """Write the two-file layout earlier versions produced; return the ACL path."""
    path = directory / "usb_acl.json"
    raw = json.dumps(payload, indent=2).encode("utf-8")
    path.write_bytes(raw)
    if signed:
        (directory / "usb_acl.json.key").write_bytes(key)
        (directory / "usb_acl.json.sig").write_text(
            hmac.new(key, raw, hashlib.sha256).hexdigest(), encoding="utf-8")
    return path


_ONE_RULE = {"version": 1, "default": "deny", "rules": [
    {"vendor_id": "1050", "product_id": "0407", "serial": None, "label": "key",
     "allow": True, "prompt_on_open": False}]}


# --- the layout -----------------------------------------------------------------------------

def test_a_save_writes_data_and_signature_into_one_file(tmp_path):
    path = tmp_path / "usb_acl.json"
    acl = UsbAcl(path=path)
    acl.add_rule(_rule(1))
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["version"] == 1
    assert len(stored["rules"]) == 1
    assert stored["signature"]["algorithm"] == "hmac-sha256"
    assert len(stored["signature"]["value"]) == 64
    assert not (tmp_path / "usb_acl.json.sig").exists()
    assert not (tmp_path / "usb_acl.json.lock").exists(), "the lock is released"
    reopened = UsbAcl(path=path)
    assert reopened.integrity_ok
    assert reopened.verify_integrity()
    assert _products(reopened) == [("1050", "0001")]


def test_the_signature_covers_the_content_not_its_formatting(tmp_path):
    path = tmp_path / "usb_acl.json"
    UsbAcl(path=path).add_rule(_rule(1))
    stored = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(stored, separators=(",", ":")), encoding="utf-8")
    assert UsbAcl(path=path).integrity_ok
    stored["rules"][0]["product_id"] = "ffff"
    path.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    tampered = UsbAcl(path=path)
    assert tampered.integrity_ok is False
    assert tampered.verify_integrity() is False
    assert tampered.list_rules() == []
    assert tampered.decide(vendor_id="1050", product_id="ffff", serial=None) == "deny"


def test_changing_the_default_without_the_key_fails_closed(tmp_path):
    path = tmp_path / "usb_acl.json"
    UsbAcl(path=path).add_rule(_rule(1))
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["default"] = "allow"
    path.write_text(json.dumps(stored), encoding="utf-8")
    acl = UsbAcl(path=path)
    assert acl.integrity_ok is False
    assert acl.decide(vendor_id="dead", product_id="beef", serial=None) == "deny"


@pytest.mark.parametrize("signature", [None, "", "abc", {"algorithm": "hmac-sha256"},
                                       {"algorithm": "none", "value": ""}, ["x"]])
def test_a_stripped_or_malformed_signature_fails_closed_once_a_key_exists(tmp_path, signature):
    path = tmp_path / "usb_acl.json"
    UsbAcl(path=path).add_rule(_rule(1))
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["default"] = "allow"
    if signature is None:
        del stored["signature"]
    else:
        stored["signature"] = signature
    path.write_text(json.dumps(stored), encoding="utf-8")
    acl = UsbAcl(path=path)
    assert acl.integrity_ok is False
    assert acl.decide(vendor_id="1050", product_id="0001", serial=None) == "deny"


def test_an_explicit_key_signs_and_verifies_the_single_file(tmp_path):
    path = tmp_path / "usb_acl.json"
    UsbAcl(path=path, hmac_key=b"a" * 32).add_rule(_rule(1))
    assert not (tmp_path / "usb_acl.json.key").exists()
    assert UsbAcl(path=path, hmac_key=b"a" * 32).integrity_ok
    assert UsbAcl(path=path, hmac_key=b"b" * 32).integrity_ok is False


# --- the two-file layout is still read -----------------------------------------------------------

def test_a_signed_two_file_acl_loads_and_is_rewritten_as_one_file(tmp_path):
    path = _legacy_layout(tmp_path, _ONE_RULE)
    acl = UsbAcl(path=path)
    assert acl.integrity_ok
    assert acl.verify_integrity()
    assert acl.decide(vendor_id="1050", product_id="0407", serial=None) == "allow"
    assert (tmp_path / "usb_acl.json.sig").exists(), "reading changes nothing on disk"
    acl.add_rule(_rule(2))
    assert not (tmp_path / "usb_acl.json.sig").exists()
    assert "signature" in json.loads(path.read_text(encoding="utf-8"))
    assert len(UsbAcl(path=path).list_rules()) == 2


def test_a_two_file_acl_with_a_wrong_signature_still_fails_closed(tmp_path):
    path = _legacy_layout(tmp_path, _ONE_RULE)
    path.write_text(json.dumps({**_ONE_RULE, "default": "allow"}), encoding="utf-8")
    acl = UsbAcl(path=path)
    assert acl.integrity_ok is False
    assert acl.list_rules() == []


def test_an_unsigned_file_from_before_signing_still_loads(tmp_path):
    path = _legacy_layout(tmp_path, _ONE_RULE, signed=False)
    acl = UsbAcl(path=path)
    assert acl.integrity_ok
    assert len(acl.list_rules()) == 1
    assert UsbAcl(path=path, require_signature=True).integrity_ok is False


# --- two instances, two processes ------------------------------------------------------------------

def _mismatches(caplog):
    return [record.getMessage() for record in caplog.records
            if "signature mismatch" in record.getMessage()
            or "no signature" in record.getMessage()]


def test_two_instances_changing_one_file_never_see_a_torn_pair(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger=autocontrol_logger.name)
    path = tmp_path / "usb_acl.json"
    UsbAcl(path=path).set_default_policy("deny")
    instances = [UsbAcl(path=path), UsbAcl(path=path)]
    failures = []

    def write(acl, vendor):
        try:
            for index in range(_PER_WRITER):
                acl.add_rule(_rule(index, vendor))
        except Exception as error:  # noqa: BLE001  # reason: handed back to the test thread
            failures.append(error)
    threads = [threading.Thread(target=write, args=(acl, vendor))
               for acl, vendor in zip(instances, ("aaaa", "bbbb"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(_WAIT)
    assert failures == []
    assert not any(thread.is_alive() for thread in threads)
    assert all(acl.integrity_ok for acl in instances)
    assert _mismatches(caplog) == []
    final = UsbAcl(path=path)
    assert final.integrity_ok
    assert len(final.list_rules()) == 2 * _PER_WRITER, "neither instance saved over the other"


_CHILD = """
import sys
from je_auto_control.utils.usb.passthrough.acl import AclRule, UsbAcl
acl = UsbAcl(path=sys.argv[1])
for index in range(int(sys.argv[2])):
    acl.add_rule(AclRule(vendor_id="cccc", product_id=f"{index:04x}", allow=True))
print("integrity", acl.integrity_ok)
"""


def test_a_child_process_and_this_one_keep_each_others_rules(tmp_path):
    path = tmp_path / "usb_acl.json"
    mine = UsbAcl(path=path)
    mine.set_default_policy("deny")
    child = subprocess.Popen(  # nosec B603  # nosemgrep  # reason: this interpreter, fixed script
        [sys.executable, "-c", _CHILD, str(path), str(_PER_WRITER)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # nosemgrep
    try:
        for index in range(_PER_WRITER):
            mine.add_rule(_rule(index, "dddd"))
        out, err = child.communicate(timeout=_WAIT)
    finally:
        if child.poll() is None:
            child.kill()
    assert child.returncode == 0, err
    assert "integrity True" in out
    assert mine.integrity_ok
    final = UsbAcl(path=path)
    assert final.integrity_ok
    vendors = [vendor for vendor, _product in _products(final)]
    assert vendors.count("cccc") == _PER_WRITER
    assert vendors.count("dddd") == _PER_WRITER


def test_a_change_that_cannot_get_the_lock_is_refused_not_applied(tmp_path, monkeypatch):
    path = tmp_path / "usb_acl.json"
    acl = UsbAcl(path=path)
    acl.add_rule(_rule(1))
    monkeypatch.setattr(json_store, "_LOCK_WAIT_S", 0.2)
    (tmp_path / "usb_acl.json.lock").write_text("held", encoding="utf-8")
    second = _rule(2)
    with pytest.raises(UsbAclBusyError):
        acl.add_rule(second)
    assert len(acl.list_rules()) == 1, "nothing changed in memory either"
    (tmp_path / "usb_acl.json.lock").unlink()
    acl.add_rule(_rule(2))
    assert len(UsbAcl(path=path).list_rules()) == 2


def test_a_directory_that_cannot_hold_a_lock_file_does_not_block_the_change(
        tmp_path, monkeypatch, caplog):
    """As before the lock existed: the rule applies and the failure is logged."""
    from contextlib import contextmanager

    from je_auto_control.utils.usb.passthrough import acl as acl_module

    @contextmanager
    def no_lock(_path):
        if _path is not None:
            raise PermissionError(13, "read-only directory")
        yield
    monkeypatch.setattr(acl_module, "_file_lock", no_lock)
    caplog.set_level(logging.WARNING, logger=autocontrol_logger.name)
    acl = UsbAcl(path=tmp_path / "usb_acl.json")
    acl.add_rule(_rule(1))
    assert len(acl.list_rules()) == 1
    assert any("without its lock file" in record.getMessage() for record in caplog.records)


def test_an_in_memory_change_needs_no_lock(tmp_path, monkeypatch):
    path = tmp_path / "usb_acl.json"
    acl = UsbAcl(path=path)
    monkeypatch.setattr(json_store, "_LOCK_WAIT_S", 0.2)
    (tmp_path / "usb_acl.json.lock").write_text("held", encoding="utf-8")
    acl.add_rule(_rule(1), persist=False)
    assert len(acl.list_rules()) == 1
    assert not path.exists()
