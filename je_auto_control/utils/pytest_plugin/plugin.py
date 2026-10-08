"""pytest plugin for AutoControl: the names of ``je_auto_control_pytest``.

The plugin itself lives in the top-level module ``je_auto_control_pytest`` so
that the ``pytest11`` entry point can load it without importing this package.
This module keeps the old import path, and
``pytest_plugins = ["je_auto_control.utils.pytest_plugin"]``, working: every
name here is the same object as there.
"""
from je_auto_control_pytest import (  # noqa: F401  # reason: the private helpers stay importable from the old path
    _capture_failure_screenshot, _resolve_dir,
    autocontrol, autocontrol_executor, autocontrol_screenshot_dir,
    pytest_configure, pytest_runtest_makereport,
)

__all__ = [
    "autocontrol", "autocontrol_executor", "autocontrol_screenshot_dir",
    "pytest_configure", "pytest_runtest_makereport",
]
