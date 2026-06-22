"""Headless tests for the WCAG 2.2 SC-tagged accessibility rule engine.
Pure stdlib; no Qt imports (elements are supplied as lightweight fakes)."""
from types import SimpleNamespace

import je_auto_control as ac
from je_auto_control.utils.a11y_audit import (
    audit_target_size, tag_issue, wcag_audit)
from je_auto_control.utils.a11y_audit.audit import AuditIssue


def _el(role, bounds, name="x"):
    return SimpleNamespace(role=role, name=name, bounds=bounds)


# --- target size (SC 2.5.8) ----------------------------------------------

def test_target_size_flags_small_interactive():
    elements = [
        _el("button", (0, 0, 20, 20)),     # too small -> flagged
        _el("button", (0, 0, 40, 40)),     # ok
        _el("text", (0, 0, 5, 5)),         # not interactive -> ignored
        _el("button", (0, 0, 0, 0)),       # unknown size -> skipped
    ]
    issues = audit_target_size(elements)
    assert len(issues) == 1
    assert issues[0].kind == "target_size"
    assert issues[0].detail == {"width": 20, "height": 20, "min_px": 24}


def test_tag_issue_carries_success_criterion():
    tagged = tag_issue(AuditIssue(kind="contrast", severity="error",
                                  message="low"))
    assert tagged["sc"] == "1.4.3"
    assert tagged["level"] == "AA"
    assert tagged["impact"] == "serious"


# --- conformance report ---------------------------------------------------

def test_wcag_audit_tags_and_filters_by_level():
    elements = [_el("button", (0, 0, 10, 10), name="")]   # small + unlabeled
    report = wcag_audit(
        elements=elements,
        contrast_pairs=[{"foreground": [120, 120, 120],
                         "background": [130, 130, 130], "label": "lbl"}],
        texts=["clipped text…"], level="AA")
    assert report["level"] == "AA"
    assert report["conformant"] is False
    scs = {f["sc"] for f in report["findings"]}
    assert {"4.1.2", "1.4.3", "1.4.10", "2.5.8"} <= scs
    assert report["total"] == len(report["findings"])
    assert sum(report["by_impact"].values()) == report["total"]


def test_wcag_audit_level_a_excludes_aa():
    report = wcag_audit(
        elements=[],
        contrast_pairs=[{"foreground": [0, 0, 0], "background": [0, 0, 0]}],
        level="A")
    # contrast (AA) is excluded at level A
    assert all(f["level"] == "A" for f in report["findings"])
    assert "1.4.3" not in {f["sc"] for f in report["findings"]}


def test_clean_scope_is_conformant():
    report = wcag_audit(elements=[_el("button", (0, 0, 48, 48))])
    assert report["conformant"] is True
    assert report["total"] == 0


# --- wiring ---------------------------------------------------------------

def test_wiring():
    # Registration only — executing AC_wcag_audit needs a live a11y backend,
    # which varies by platform; the functional path is covered above.
    assert "AC_wcag_audit" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    assert "ac_wcag_audit" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_wcag_audit" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("wcag_audit", "audit_target_size"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
