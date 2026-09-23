"""USB passthrough ACL defects from the 2026-09-24 audit (temp files only).

Deleting the ``.sig`` next to a rewritten file passed as a legacy unsigned
ACL; a damaged file was replaced by the next save; malformed rule ids were
stored and never matched; ``remove_rule`` compared ids differently from
``matches``; and two instances overwrote each other's rules.
"""
import json

import pytest

from je_auto_control.utils.usb.passthrough.acl import AclRule, UsbAcl


def _signed_acl(tmp_path, rules=()):
    path = tmp_path / "usb_acl.json"
    acl = UsbAcl(path=path, default_policy="allow")
    for vendor, product, allow in rules:
        acl.add_rule(AclRule(vendor_id=vendor, product_id=product, allow=allow))
    acl.set_default_policy("allow")
    return path


def test_deleting_the_signature_does_not_make_a_legacy_file(tmp_path):
    path = _signed_acl(tmp_path, [("1050", "0407", False)])
    path.write_text(json.dumps({"version": 1, "default": "allow", "rules": []}), encoding="utf-8")
    (tmp_path / "usb_acl.json.sig").unlink()
    acl = UsbAcl(path=path)
    assert acl.integrity_ok is False
    assert acl.decide(vendor_id="1050", product_id="0407", serial=None) == "deny"


def test_a_damaged_file_is_kept_aside_not_overwritten(tmp_path):
    path = _signed_acl(tmp_path, [("aaaa", "0001", True), ("bbbb", "0002", True)])
    damaged = path.read_bytes()[:-3]
    path.write_bytes(damaged)
    (tmp_path / "usb_acl.json.sig").unlink()
    (tmp_path / "usb_acl.json.key").unlink()
    acl = UsbAcl(path=path)
    assert acl.decide(vendor_id="aaaa", product_id="0001", serial=None) == "deny"
    kept = [p for p in tmp_path.iterdir() if p.name.startswith("usb_acl.json.corrupt-")]
    assert len(kept) == 1 and kept[0].read_bytes() == damaged


@pytest.mark.parametrize("vendor, product", [("01050", "0407"), ("1050:0407", "0407"), ("10_50", "0407")])
def test_a_malformed_rule_id_is_refused(vendor, product):
    with pytest.raises(ValueError):
        AclRule(vendor_id=vendor, product_id=product, allow=False)


def test_rule_ids_are_normalised():
    rule = AclRule(vendor_id="0x1050", product_id="0407", allow=False)
    assert (rule.vendor_id, rule.product_id) == ("1050", "0407")


def test_a_rule_can_be_removed_by_any_spelling_of_its_id(tmp_path):
    acl = UsbAcl(path=tmp_path / "usb_acl.json", default_policy="allow")
    acl.add_rule(AclRule(vendor_id="0x1050", product_id="0407", allow=False))
    assert acl.remove_rule(vendor_id="1050", product_id="0X0407") is True
    assert acl.decide(vendor_id="1050", product_id="0407", serial=None) == "allow"


def test_two_instances_keep_each_others_rules(tmp_path):
    path = tmp_path / "usb_acl.json"
    first, second = UsbAcl(path=path), UsbAcl(path=path)
    first.add_rule(AclRule(vendor_id="1111", product_id="0001", allow=False))
    second.add_rule(AclRule(vendor_id="2222", product_id="0002", allow=True))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(rule["vendor_id"] for rule in saved["rules"]) == ["1111", "2222"]


def test_a_usb_error_without_errno_is_eio():
    from je_auto_control.utils.usbip.libusb_backend import _translate_error
    usb_error = type("USBError", (Exception,), {})("Other error")
    usb_error.errno = None
    assert _translate_error(usb_error) == -5
    usb_error.errno = 19
    assert _translate_error(usb_error) == -19
