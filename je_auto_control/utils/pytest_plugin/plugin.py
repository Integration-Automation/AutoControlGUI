"""Compatibility import for the lightweight top-level pytest plugin."""
# pylint: disable=useless-import-alias  # reason: explicit aliases preserve private helper re-exports
from je_auto_control_pytest import (
    _capture_failure_screenshot as _capture_failure_screenshot,
    _resolve_dir as _resolve_dir,
    autocontrol, autocontrol_executor, autocontrol_screenshot_dir,
    pytest_configure, pytest_runtest_makereport,
)

__all__ = [
    "autocontrol", "autocontrol_executor", "autocontrol_screenshot_dir",
    "pytest_configure", "pytest_runtest_makereport",
]
