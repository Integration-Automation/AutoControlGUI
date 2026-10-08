"""A USB ACL whose file fails its integrity check denies everything.

``UsbAcl(path, default_policy="allow")`` used to keep the constructor's
default when the file failed its check: ``integrity_ok`` said ``False`` and
``decide()`` still answered ``"allow"``. Temp files only.
"""
import json

import pytest

from je_auto_control.utils.usb.passthrough.acl import AclRule, UsbAcl

_DEVICE = {"vendor_id": "1050", "product_id": "0407", "serial": None}
_OTHER = {"vendor_id": "dead", "product_id": "beef", "serial": None}


def _signed_file(tmp_path, *, default="allow", prompt=False):
    """An intact ACL holding one rule for ``_DEVICE``; return its path."""
    path = tmp_path / "usb_acl.json"
    acl = UsbAcl(path=path, default_policy=default)
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True, prompt_on_open=prompt))
    acl.set_default_policy(default)
    return path


def _tamper(path) -> None:
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["rules"].append({"vendor_id": "dead", "product_id": "beef", "serial": None,
                            "label": "", "allow": True, "prompt_on_open": False})
    path.write_text(json.dumps(stored), encoding="utf-8")


@pytest.mark.parametrize("default_policy", ["allow", "deny"])
def test_a_tampered_file_denies_whatever_the_default_policy(tmp_path, default_policy):
    path = _signed_file(tmp_path)
    _tamper(path)
    acl = UsbAcl(path=path, default_policy=default_policy)
    assert acl.integrity_ok is False
    assert acl.decide(**_OTHER) == "deny"
    assert acl.decide(**_DEVICE) == "deny"
    assert acl.default_policy == "deny"


def test_an_intact_allow_file_still_allows(tmp_path):
    acl = UsbAcl(path=_signed_file(tmp_path), default_policy="allow")
    assert acl.integrity_ok is True
    assert acl.decide(**_OTHER) == "allow"
    assert acl.decide(**_DEVICE) == "allow"
    assert acl.default_policy == "allow"


def test_a_missing_file_keeps_the_constructor_default(tmp_path):
    acl = UsbAcl(path=tmp_path / "usb_acl.json", default_policy="allow")
    assert acl.integrity_ok is True
    assert acl.decide(**_OTHER) == "allow"


def test_tampering_seen_on_a_later_read_also_denies_rules_loaded_before(tmp_path):
    path = _signed_file(tmp_path, prompt=True)
    acl = UsbAcl(path=path, default_policy="allow")
    assert acl.decide(**_DEVICE) == "prompt"
    _tamper(path)
    # Removing a rule that is not there re-reads the file and saves nothing.
    assert acl.remove_rule(vendor_id="ffff", product_id="ffff") is False
    assert acl.integrity_ok is False
    assert acl.decide(**_DEVICE) == "deny"
    assert acl.decide(**_OTHER) == "deny"


def test_a_save_by_the_operator_ends_the_lockdown(tmp_path):
    path = _signed_file(tmp_path)
    _tamper(path)
    acl = UsbAcl(path=path, default_policy="allow")
    assert acl.decide(**_OTHER) == "deny"
    acl.set_default_policy("allow")
    assert acl.integrity_ok is True
    assert acl.decide(**_OTHER) == "allow"
    assert UsbAcl(path=path).integrity_ok is True


def test_an_intact_file_read_after_a_bad_one_is_trusted_again(tmp_path):
    path = _signed_file(tmp_path)
    good = path.read_bytes()
    _tamper(path)
    acl = UsbAcl(path=path, default_policy="allow")
    assert acl.integrity_ok is False
    path.write_bytes(good)
    assert acl.remove_rule(vendor_id="ffff", product_id="ffff") is False  # re-reads only
    assert acl.integrity_ok is True
    assert acl.decide(**_DEVICE) == "allow"
