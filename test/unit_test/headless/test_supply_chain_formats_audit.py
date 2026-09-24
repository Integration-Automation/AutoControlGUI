"""Supply-chain formats follow their specs at the edges (pure).

OpenVEX "affected" needs an action statement; SLSA provenance leaves out
empty metadata and verifies nameless subjects; PEP 440 orders post/dev
releases and implicit numbers; redaction boxes merge transitively.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.provenance.provenance import (
    build_provenance, subject_for_bytes, verify_provenance,
)
from je_auto_control.utils.redaction.rules import merge_boxes
from je_auto_control.utils.vex.vex import vex_statement
from je_auto_control.utils.vuln_scan.vuln_scan import version_key


def test_an_affected_statement_needs_an_action_statement():
    with pytest.raises(AutoControlException, match="action_statement"):
        vex_statement("CVE-2024-1", "affected")
    statement = vex_statement("CVE-2024-1", "affected", action_statement="Upgrade to 2.1")
    assert statement["action_statement"] == "Upgrade to 2.1"


def test_provenance_leaves_out_empty_timestamps():
    statement = build_provenance([subject_for_bytes("a.txt", b"x")])
    metadata = statement["predicate"]["runDetails"]["metadata"]
    assert "startedOn" not in metadata and "finishedOn" not in metadata


def test_a_nameless_subject_is_reported_not_raised(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"x")
    statement = {"subject": [{"digest": {"sha256": "0" * 64}}]}
    mismatches = verify_provenance(statement, {"a.txt": str(path)})
    assert mismatches and mismatches[0]["name"] == "a.txt"


@pytest.mark.parametrize("lower, higher", [
    ("1.0.post1.dev1", "1.0.post1"),
    ("1.0", "1.0.post1.dev1"),
    ("1.0.dev1", "1.0a1"),
    ("1.0a1.dev1", "1.0a1"),
])
def test_pep_440_post_and_dev_order(lower, higher):
    assert version_key(lower) < version_key(higher)


@pytest.mark.parametrize("implicit, explicit", [
    ("1.0b", "1.0b0"), ("1.0.post", "1.0.post0"), ("1.0.dev", "1.0.dev0"),
])
def test_an_omitted_number_is_zero(implicit, explicit):
    assert version_key(implicit) == version_key(explicit)


def test_boxes_merge_until_none_overlap():
    merged = merge_boxes([(0, 0, 10, 10), (100, 0, 110, 10), (5, 5, 105, 6)])
    assert merged == [(0, 0, 110, 10)]
    assert merge_boxes([(0, 0, 5, 5), (10, 10, 15, 15)]) == [(0, 0, 5, 5), (10, 10, 15, 15)]
