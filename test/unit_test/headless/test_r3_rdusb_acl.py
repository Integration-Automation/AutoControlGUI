"""Audit round 3 regression for the USB passthrough ACL (finding 11).

vid/pid are hex strings and must compare case-insensitively; otherwise a rule
written in one case silently fails to match a device reporting the other case,
which bypasses a DENY rule when the default policy is "allow".
"""
from je_auto_control.utils.usb.passthrough.acl import AclRule, UsbAcl


def test_uppercase_deny_rule_matches_lowercase_device(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json", default_policy="allow")
    acl.add_rule(
        AclRule(vendor_id="1D6B", product_id="0002", allow=False),
        persist=False,
    )
    # Device reports lowercase hex; the uppercase DENY rule must still apply.
    assert acl.decide(vendor_id="1d6b", product_id="0002",
                      serial=None) == "deny"


def test_lowercase_deny_rule_matches_uppercase_device(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json", default_policy="allow")
    acl.add_rule(
        AclRule(vendor_id="1d6b", product_id="0002", allow=False),
        persist=False,
    )
    assert acl.decide(vendor_id="1D6B", product_id="0002",
                      serial=None) == "deny"


def test_non_matching_vid_still_falls_through_to_default(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json", default_policy="allow")
    acl.add_rule(
        AclRule(vendor_id="1D6B", product_id="0002", allow=False),
        persist=False,
    )
    # A genuinely different device is unaffected by the rule.
    assert acl.decide(vendor_id="dead", product_id="beef",
                      serial=None) == "allow"


def test_rule_matches_predicate_is_case_insensitive():
    rule = AclRule(vendor_id="ABCD", product_id="00FF")
    assert rule.matches(vendor_id="abcd", product_id="00ff", serial=None)
    assert rule.matches(vendor_id="ABCD", product_id="00FF", serial=None)
