"""Headless tests for the accessibility / i18n audit."""
from types import SimpleNamespace

import pytest

import je_auto_control as ac
from je_auto_control.utils.a11y_audit import (
    audit_contrast, audit_missing_labels, contrast_ratio, detect_truncation,
    is_interactive, run_audit,
)


def _el(name, role):
    return SimpleNamespace(name=name, role=role, bounds=(0, 0, 10, 10))


def test_facade_exports():
    assert hasattr(ac, "run_audit")
    assert hasattr(ac, "contrast_ratio")


def test_is_interactive():
    assert is_interactive("Button")
    assert is_interactive("menu item")
    assert not is_interactive("StaticText")


def test_missing_label_flagged():
    issues = audit_missing_labels([
        _el("", "button"), _el("OK", "button"), _el("", "StaticText"),
    ])
    assert len(issues) == 1
    assert issues[0].kind == "missing_label"
    assert issues[0].severity == "error"


def test_contrast_ratio_known_values():
    # black on white is the maximum 21:1
    assert contrast_ratio([0, 0, 0], [255, 255, 255]) == pytest.approx(21.0)
    # identical colours are 1:1
    assert contrast_ratio([120, 120, 120], [120, 120, 120]) == pytest.approx(1.0)


def test_audit_contrast_flags_low():
    issues = audit_contrast([
        {"foreground": [200, 200, 200], "background": [255, 255, 255],
         "label": "faint"},
        {"foreground": [0, 0, 0], "background": [255, 255, 255],
         "label": "strong"},
    ])
    assert len(issues) == 1
    assert issues[0].target == "faint"


def test_detect_truncation():
    issues = detect_truncation(["Hello", "This is clipped…", "More..."])
    assert len(issues) == 2
    assert all(i.kind == "truncation" for i in issues)


def test_run_audit_combines_inputs():
    report = run_audit(
        elements=[_el("", "button")],
        contrast_pairs=[{"foreground": [200, 200, 200],
                         "background": [255, 255, 255], "label": "x"}],
        texts=["clipped…"],
    )
    kinds = {i.kind for i in report.issues}
    assert kinds == {"missing_label", "contrast", "truncation"}
    assert report.error_count >= 2
    assert report.warning_count == 1


def test_executor_audit_contrast():
    from je_auto_control.utils.executor.action_executor import executor
    out = executor.event_dict["AC_audit_contrast"]([0, 0, 0], [255, 255, 255])
    assert out["passes_aa"] is True
    assert out["ratio"] == pytest.approx(21.0)
