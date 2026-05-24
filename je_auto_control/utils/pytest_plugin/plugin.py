"""pytest plugin for AutoControl.

Exposes:

* ``autocontrol`` fixture — the package module itself, so a test can
  call ``autocontrol.screen_size()`` without re-importing it;
* ``autocontrol_screenshot_dir`` fixture — a ``pathlib.Path`` to
  ``tmp_path/'autocontrol_screenshots'``; created on first access;
* ``@pytest.mark.autocontrol`` marker — when a test marked with it
  fails, the plugin captures a screenshot to the screenshot dir and
  attaches the path to the failure report.

Registered via the ``pytest11`` entry point so installing
``je_auto_control`` makes the plugin available automatically.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pytest


_MARKER_NAME = "autocontrol"
_DEFAULT_SUBDIR = "autocontrol_screenshots"


def pytest_configure(config: "pytest.Config") -> None:
    """Register the ``autocontrol`` marker so ``--strict-markers`` is happy."""
    config.addinivalue_line(
        "markers",
        f"{_MARKER_NAME}: AutoControl GUI test; capture a screenshot on failure.",
    )


@pytest.fixture
def autocontrol():
    """Return the ``je_auto_control`` module without forcing a global import."""
    import je_auto_control
    return je_auto_control


@pytest.fixture
def autocontrol_screenshot_dir(tmp_path) -> Path:
    """Per-test directory under ``tmp_path`` for screenshots / artefacts."""
    target = tmp_path / _DEFAULT_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture
def autocontrol_executor():
    """Yield the executor singleton (callable via ``executor.event_dict``)."""
    from je_auto_control.utils.executor.action_executor import executor
    return executor


def _capture_failure_screenshot(item: "pytest.Item",
                                 directory: Path) -> Optional[Path]:
    """Best-effort screenshot capture on failure; returns the path or None."""
    name = item.nodeid.replace("/", "_").replace("::", "__")
    target = directory / f"{name}.png"
    try:
        from je_auto_control.wrapper.auto_control_screen import screenshot
        screenshot(file_path=str(target))
    except (OSError, RuntimeError, ValueError) as exc:
        item.add_report_section(
            "call", "autocontrol-screenshot",
            f"failed to capture screenshot: {exc!r}",
        )
        return None
    return target


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):  # noqa: D401
    """Attach a screenshot path to the failure report for ``autocontrol`` tests."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or report.passed:
        return
    if item.get_closest_marker(_MARKER_NAME) is None:
        return
    directory = _resolve_dir(item)
    captured = _capture_failure_screenshot(item, directory)
    if captured is not None:
        report.sections.append(
            ("autocontrol-screenshot", f"screenshot: {captured}"),
        )


def _resolve_dir(item: "pytest.Item") -> Path:
    """Pick the per-test ``autocontrol_screenshot_dir`` if it exists."""
    funcargs = getattr(item, "funcargs", {}) or {}
    directory = funcargs.get("autocontrol_screenshot_dir")
    if isinstance(directory, Path):
        return directory
    fallback = Path(os.environ.get(
        "JE_AUTOCONTROL_PYTEST_ARTIFACTS",
        str(Path.cwd() / _DEFAULT_SUBDIR),
    ))
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


__all__ = [
    "autocontrol", "autocontrol_executor", "autocontrol_screenshot_dir",
    "pytest_configure", "pytest_runtest_makereport",
]
