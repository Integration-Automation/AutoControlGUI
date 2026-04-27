"""CLI: ``python -m je_auto_control.utils.diagnostics``.

Prints one line per check with a colored severity tag and exits 0 if no
errors were detected, 1 otherwise. Useful as a smoke test in CI.
"""
from __future__ import annotations

import sys
from typing import Optional

from je_auto_control.utils.diagnostics.diagnostics import run_diagnostics


_SEVERITY_TAG = {
    "info": "OK   ",
    "warn": "WARN ",
    "error": "FAIL ",
}


def main(_argv: Optional[list] = None) -> int:
    report = run_diagnostics()
    for check in report.checks:
        tag = _SEVERITY_TAG.get(check.severity, "?    ")
        print(f"[{tag}] {check.name}: {check.detail}")
    summary = report.to_dict()
    print(
        f"\nSummary: {summary['count']} checks, "
        f"{summary['failed']} failed, status={'OK' if report.ok else 'FAIL'}"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
