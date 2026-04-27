"""Run a battery of small subsystem checks and report status.

Each check is a small function returning a :class:`Check`. The runner
catches *every* exception per-check so one broken probe never poisons
the rest — diagnostics that fail to run are themselves diagnostic
information, so we surface them as a check with ``ok=False``.
"""
from __future__ import annotations

import importlib
import os
import platform
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_SEVERITY_INFO = "info"
_SEVERITY_WARN = "warn"
_SEVERITY_ERROR = "error"


@dataclass
class Check:
    """One subsystem probe result."""

    name: str
    ok: bool
    severity: str
    detail: str
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticsReport:
    """Full output of :func:`run_diagnostics`."""

    checks: List[Check]

    @property
    def ok(self) -> bool:
        return all(
            check.ok or check.severity == _SEVERITY_INFO
            for check in self.checks
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "count": len(self.checks),
            "failed": sum(1 for c in self.checks
                          if not c.ok and c.severity != _SEVERITY_INFO),
        }


CheckFn = Callable[[], Check]


def run_diagnostics() -> DiagnosticsReport:
    """Run every registered check; return a :class:`DiagnosticsReport`."""
    checks: List[Check] = []
    for runner in _ALL_CHECKS:
        try:
            checks.append(runner())
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: never let one probe poison the rest
            autocontrol_logger.warning(
                "diagnostics check %s crashed: %r", runner.__name__, error,
            )
            checks.append(Check(
                name=runner.__name__.replace("_check_", ""),
                ok=False, severity=_SEVERITY_ERROR,
                detail=f"check raised: {error!r}",
            ))
    return DiagnosticsReport(checks=checks)


def _check_platform() -> Check:
    return Check(
        name="platform",
        ok=True,
        severity=_SEVERITY_INFO,
        detail=f"{platform.system()} {platform.release()} / "
               f"Python {platform.python_version()}",
    )


def _check_optional_deps() -> Check:
    optional_modules: Tuple[Tuple[str, str], ...] = (
        ("aiortc", "remote desktop / WebRTC"),
        ("av", "WebRTC video codec"),
        ("usb.core", "USB enumeration via pyusb"),
        ("pyaudio", "microphone capture"),
        ("pytesseract", "OCR engine"),
        ("cv2", "image recognition"),
        ("PySide6", "GUI"),
    )
    available, missing = [], []
    for module_name, purpose in optional_modules:
        try:
            importlib.import_module(module_name)
            available.append(module_name)
        except ImportError:
            missing.append(f"{module_name} ({purpose})")
    return Check(
        name="optional_deps",
        ok=True,
        severity=_SEVERITY_INFO if not missing else _SEVERITY_WARN,
        detail=f"available: {len(available)}, missing: {len(missing)}",
        extra={"available": available, "missing": missing},
    )


def _check_audit_chain() -> Check:
    from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
    result = default_audit_log().verify_chain()
    if result.ok:
        return Check(
            name="audit_chain", ok=True, severity=_SEVERITY_INFO,
            detail=f"chain verified ({result.total_rows} rows)",
        )
    return Check(
        name="audit_chain", ok=False, severity=_SEVERITY_ERROR,
        detail=f"chain broken at id {result.broken_at_id} "
               f"(of {result.total_rows} rows)",
        extra={"broken_at_id": result.broken_at_id},
    )


def _check_screenshot() -> Check:
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    image = pil_screenshot()
    width, height = image.size
    if width < 1 or height < 1:
        return Check(
            name="screenshot", ok=False, severity=_SEVERITY_ERROR,
            detail=f"degenerate image: {width}x{height}",
        )
    return Check(
        name="screenshot", ok=True, severity=_SEVERITY_INFO,
        detail=f"captured {width}x{height}",
    )


def _check_mouse() -> Check:
    from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
    pos = get_mouse_position()
    if pos is None:
        return Check(
            name="mouse", ok=False, severity=_SEVERITY_WARN,
            detail="get_mouse_position returned None",
        )
    return Check(
        name="mouse", ok=True, severity=_SEVERITY_INFO,
        detail=f"position {pos[0]}, {pos[1]}",
    )


def _check_disk_space() -> Check:
    home = os.path.expanduser("~")
    usage = shutil.disk_usage(home)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < 100:
        return Check(
            name="disk_space", ok=False, severity=_SEVERITY_ERROR,
            detail=f"only {free_mb:.0f} MB free in home dir",
        )
    if free_mb < 1024:
        return Check(
            name="disk_space", ok=True, severity=_SEVERITY_WARN,
            detail=f"{free_mb:.0f} MB free in home dir (low)",
        )
    return Check(
        name="disk_space", ok=True, severity=_SEVERITY_INFO,
        detail=f"{free_mb / 1024:.1f} GB free in home dir",
    )


def _check_rest_registry() -> Check:
    from je_auto_control.utils.rest_api.rest_registry import rest_api_registry
    status = rest_api_registry.status()
    if not status["running"]:
        return Check(
            name="rest_api", ok=True, severity=_SEVERITY_INFO,
            detail="REST API not running",
        )
    return Check(
        name="rest_api", ok=True, severity=_SEVERITY_INFO,
        detail=f"REST API at {status['url']}",
    )


def _check_executor() -> Check:
    from je_auto_control.utils.executor.action_executor import executor
    command_count = len(executor.event_dict)
    if command_count < 1:
        return Check(
            name="executor", ok=False, severity=_SEVERITY_ERROR,
            detail="no AC_* commands registered",
        )
    return Check(
        name="executor", ok=True, severity=_SEVERITY_INFO,
        detail=f"{command_count} AC_* commands registered",
    )


_ALL_CHECKS: Tuple[CheckFn, ...] = (
    _check_platform,
    _check_optional_deps,
    _check_executor,
    _check_audit_chain,
    _check_screenshot,
    _check_mouse,
    _check_disk_space,
    _check_rest_registry,
)


__all__ = ["Check", "DiagnosticsReport", "run_diagnostics"]
