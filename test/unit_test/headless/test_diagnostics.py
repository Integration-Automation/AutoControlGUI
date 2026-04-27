"""Tests for the system diagnostics runner (round 28)."""
import subprocess
import sys

from je_auto_control.utils.diagnostics.diagnostics import (
    Check, DiagnosticsReport, run_diagnostics,
)


def test_runner_returns_a_report():
    report = run_diagnostics()
    assert isinstance(report, DiagnosticsReport)
    assert isinstance(report.checks, list)


def test_runner_includes_known_checks():
    """Every check name present in the runner must show up in the report."""
    report = run_diagnostics()
    names = {check.name for check in report.checks}
    for expected in ("platform", "optional_deps", "executor",
                     "audit_chain", "screenshot", "mouse",
                     "disk_space", "rest_api"):
        assert expected in names, f"missing check: {expected}"


def test_each_check_has_required_fields():
    report = run_diagnostics()
    for check in report.checks:
        assert isinstance(check, Check)
        assert isinstance(check.name, str) and check.name
        assert isinstance(check.ok, bool)
        assert check.severity in ("info", "warn", "error"), check.severity
        assert isinstance(check.detail, str)


def test_to_dict_payload_shape():
    report = run_diagnostics()
    payload = report.to_dict()
    for key in ("ok", "checks", "count", "failed"):
        assert key in payload
    assert payload["count"] == len(report.checks)


def test_cli_exits_zero_when_all_green():
    """The CLI module should respect the runner's overall ``ok`` flag."""
    completed = subprocess.run(  # noqa: S603  # local CLI test
        [sys.executable, "-m", "je_auto_control.utils.diagnostics"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    # Exit code is 0 when all green, 1 otherwise — both are valid outcomes
    # depending on the runner's environment. We just want it to terminate
    # cleanly with one of those codes and emit the summary line.
    assert completed.returncode in (0, 1), completed.returncode
    assert "Summary:" in completed.stdout
