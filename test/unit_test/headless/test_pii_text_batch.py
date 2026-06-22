"""Headless tests for text PII detection/redaction. Pure stdlib, no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.pii_text import detect_pii, redact_pii_text


def test_detect_each_kind():
    text = ("mail a@b.com phone +1 415-555-1234 ssn 123-45-6789 "
            "card 4111 1111 1111 1111 ip 10.0.0.1 iban DE89370400440532013000")
    kinds = {f.kind for f in detect_pii(text)}
    assert kinds == {"email", "phone", "ssn", "credit_card", "ipv4", "iban"}


def test_findings_have_spans():
    text = "reach a@b.com please"
    finding = detect_pii(text, kinds=["email"])[0]
    assert finding.value == "a@b.com"
    assert text[finding.start:finding.end] == "a@b.com"


def test_kinds_filter():
    text = "a@b.com 10.0.0.1"
    assert {f.kind for f in detect_pii(text, kinds=["ipv4"])} == {"ipv4"}


def test_overlap_credit_card_not_also_phone():
    # a 16-digit card must be reported once as credit_card, not also phone
    findings = detect_pii("pay 4111 1111 1111 1111 now")
    assert [f.kind for f in findings] == ["credit_card"]


def test_redact_label_default():
    assert redact_pii_text("contact a@b.com now") == "contact [email] now"


def test_redact_modes():
    assert redact_pii_text("a@b.com", mode="mask") == "*******"
    assert redact_pii_text("4111111111111111", mode="partial") == \
        "************1111"
    out = redact_pii_text("a@b.com", mode="hash")
    assert out.startswith("[email:") and out.endswith("]")


def test_no_pii_unchanged():
    assert redact_pii_text("nothing to see here") == "nothing to see here"
    assert detect_pii("nothing to see here") == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_redact_pii",
        {"text": "email a@b.com", "mode": "label"},
    ]])
    out = next(v for v in rec.values() if isinstance(v, dict) and "text" in v)
    assert out["text"] == "email [email]"

    rec2 = ac.execute_action([["AC_detect_pii", {"text": "a@b.com"}]])
    findings = next(v for v in rec2.values() if isinstance(v, dict)
                    and "findings" in v)["findings"]
    assert findings[0]["kind"] == "email"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_detect_pii", "AC_redact_pii"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_detect_pii", "ac_redact_pii"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_detect_pii", "AC_redact_pii"} <= cmds


def test_facade_exports():
    for attr in ("PIIFinding", "detect_pii", "redact_pii_text"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
