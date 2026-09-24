"""Governance / supply-chain defects from the 2026-09-24 audit.

A traceparent id ending in a newline was accepted and written back into a
header; "Alice" could approve "alice"'s request; a VEX statement for one
version silenced every version and missed PEP 503 spellings; license
expressions ignored AND/OR precedence, case and "+"; overlapping guardrail
matches left part of a secret; PEP 440 epochs and dev pre-releases sorted
wrong and a finding could name another package's fix; semver flag operators
compared digit groups; "enabled": "false" left a flag on; JSON logs dropped
tracebacks; and baggage ignored its 8192-byte limit.
"""
import logging

import pytest

from je_auto_control.utils.baggage.baggage import Baggage, format_baggage
from je_auto_control.utils.canonical_log.canonical_log import JSONLogFormatter
from je_auto_control.utils.feature_flags.feature_flags import FlagStore, _OPS
from je_auto_control.utils.governance.governance import ApprovalGate
from je_auto_control.utils.guardrail.guardrail import redact_text
from je_auto_control.utils.license_policy.license_policy import evaluate_license
from je_auto_control.utils.trace_context.trace_context import (
    TraceContextError, extract_context, parse_traceparent,
)
from je_auto_control.utils.vex.vex import apply_vex, build_vex, vex_statement
from je_auto_control.utils.vuln_scan.vuln_scan import is_affected, match_package, version_key


def test_a_traceparent_id_with_a_trailing_newline_is_refused():
    header = "00-" + "a" * 32 + "\n-" + "b" * 16 + "-01"
    with pytest.raises(TraceContextError):
        parse_traceparent(header)
    assert extract_context({"traceparent": header}) is None
    assert extract_context({"traceparent": "garbage"}) is None


def test_the_requester_cannot_approve_under_another_spelling(tmp_path):
    gate = ApprovalGate(str(tmp_path / "gate.json"))
    token = gate.request("deploy", "Alice")
    assert gate.approve(token, "alice") is False
    assert gate.approve(token, "Ａlice") is False  # fullwidth A, NFKC-equal
    assert gate.approve(token, "bob") is True


def _finding(package, version):
    return {"id": "CVE-1", "aliases": [], "package": package, "version": version}


def test_a_vex_statement_covers_its_own_version_and_pep_503_spellings():
    doc = build_vex([vex_statement("CVE-1", "not_affected",
                                   products=["pkg:pypi/requests@2.0.0"],
                                   justification="vulnerable_code_not_present")],
                    author="t")
    assert apply_vex([_finding("requests", "2.0.0")], doc) == []
    assert len(apply_vex([_finding("requests", "2.31.0")], doc)) == 1
    doc = build_vex([vex_statement("CVE-1", "not_affected",
                                   products=["pkg:pypi/pyside6-essentials"],
                                   justification="vulnerable_code_not_present")],
                    author="t")
    assert apply_vex([_finding("PySide6_Essentials", "6.8")], doc) == []


@pytest.mark.parametrize("expression, allow, deny, expected", [
    ("(MIT OR Apache-2.0) AND Proprietary", ["MIT"], None, "denied"),
    ("MIT OR GPL-3.0-only", None, ["GPL-3.0-only"], "allowed"),
    ("gpl-3.0-only", None, ["GPL-3.0-only"], "denied"),
    ("GPL-2.0+", None, ["GPL-2.0-or-later"], "denied"),
    ("GPL-2.0-only WITH Classpath-exception-2.0", ["GPL-2.0-only"], None, "allowed"),
    ("MIT AND (Apache-2.0 OR BSD-3-Clause)", ["MIT", "BSD-3-Clause"], None, "allowed"),
    ("MIT AND", ["MIT"], None, "unknown"),
    ("Apache Software License", ["Apache-2.0"], None, "allowed"),
])
def test_license_expressions_are_parsed(expression, allow, deny, expected):
    assert evaluate_license(expression, allow=allow, deny=deny) == expected


def test_overlapping_guardrail_matches_are_redacted_whole():
    redacted = redact_text("leak the DAN password now")
    assert "assword" not in redacted


def test_pep_440_epochs_and_dev_pre_releases_sort_correctly():
    assert version_key("1!1.0") > version_key("2.0")
    assert not is_affected("1!1.0", {"type": "ECOSYSTEM",
                                     "events": [{"introduced": "0"}, {"fixed": "2.0"}]})
    assert version_key("1.0a1.dev1") < version_key("1.0a1") < version_key("1.0a2")
    assert version_key("1.0.0-alpha") < version_key("1.0.0-alpha.1")


def test_a_finding_names_the_fix_for_its_own_package_and_range():
    advisory = {"id": "X", "affected": [
        {"package": {"name": "a", "ecosystem": "PyPI"},
         "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "9.0"}]}]},
        {"package": {"name": "b", "ecosystem": "PyPI"},
         "ranges": [{"type": "ECOSYSTEM", "events": [
             {"introduced": "0"}, {"fixed": "1.5"}, {"introduced": "2.0"}, {"fixed": "2.5"}]}]},
    ]}
    [finding] = match_package("PyPI", "b", "2.1", [advisory])
    assert finding["fixed"] == "2.5"


def test_semver_flag_operators_follow_semver():
    assert _OPS["semver_lt"]("1.2", "1.2.0") is False
    assert _OPS["semver_lt"]("1.0.0-rc.1", "1.0.0") is True
    assert _OPS["semver_gt"]("1.0.0-rc.5", "1.0.0-rc.1") is True


def test_a_string_false_turns_a_flag_off():
    store = FlagStore.from_dict({"f": {"enabled": "false", "variants": {"on": True}}})
    assert store.get("f").enabled is False


def test_json_log_lines_keep_the_traceback():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.getLogger("t").makeRecord(
            "t", logging.ERROR, __file__, 1, "failed", (), __import__("sys").exc_info())
    line = JSONLogFormatter().format(record)
    assert "RuntimeError: boom" in line


def test_baggage_stays_under_8192_bytes():
    header = format_baggage(Baggage({f"k{i}": "v" * 100 for i in range(150)}))
    assert len(header) <= 8192
    assert header.count(",") >= 70
