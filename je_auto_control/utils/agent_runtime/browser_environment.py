"""Closed browser Python dependency reports; probing never starts Playwright or a browser."""
from __future__ import annotations

import re
import sys
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption

_FLAGS = ("sdk", "readback_contract", "transfer_contract", "playwright")
_KEYS = frozenset((*_FLAGS, "python", "status", "browser_launch", "native_evidence"))


def _sdk_capabilities() -> tuple[bool, bool, bool]:
    try:
        # pylint: disable-next=import-outside-toplevel  # reason: optional SDK is inspected only in the probe helper
        from je_web_runner.api.ai import ManagedBrowserSession
    except ImportError:
        return False, False, False
    version = getattr(ManagedBrowserSession, "contract_version", None)
    readback = isinstance(version, int) and not isinstance(version, bool) and version == 1
    # pylint: disable-next=import-outside-toplevel  # reason: reuse the startup contract without an eager target import
    from je_auto_control.utils.agent_runtime.browser_target import _require_transfers
    try:
        _require_transfers(ManagedBrowserSession)
        transfer = True
    except AgentTaskError:
        transfer = False
    return True, readback, transfer


def _runtime_available() -> bool:
    try:
        # pylint: disable-next=import-outside-toplevel,import-error  # reason: optional SDK owns runtime loading
        from je_web_runner.webdriver.playwright_wrapper import _require_playwright
        factory = _require_playwright()
    # pylint: disable-next=broad-exception-caught  # reason: optional SDKs have a foreign exception hierarchy
    except Exception as error:  # reason: dependency failures become metadata while interruptions propagate
        raise_caused_run_interruption(error)
        return False
    return callable(factory)  # The SDK owns the import/ABI check; do not start its returned factory.


def _report(python: str, flags: tuple[bool, bool, bool, bool], transfer: bool) -> dict[str, Any]:
    sdk, readback, transfers, runtime = flags
    if not sdk or not runtime:
        status = "dependency_missing"
    elif not readback or (transfer and not transfers):
        status = "incompatible"
    else:
        status = "python_dependencies_ready"
    return {"python": python, **dict(zip(_FLAGS, flags)), "status": status,
            "browser_launch": "not_probed", "native_evidence": "not_recorded"}


def inspect_browser_dependencies(transfer: bool) -> dict[str, Any]:
    """Import only installed Python dependencies; no downloads, driver startup or native permission requests."""
    if not isinstance(transfer, bool):
        raise AgentTaskError("browser dependency probe requires a boolean transfer flag")
    sdk, readback, transfers = _sdk_capabilities()
    runtime = _runtime_available()
    python = ".".join(str(value) for value in sys.version_info[:3])
    return _report(python, (sdk, readback, transfers, runtime), transfer)


def validate_browser_probe(value: Any, transfer: bool) -> dict[str, Any]:
    """Accept only bounded metadata with a recomputed dependency status and no native-success claim."""
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise AgentTaskError("invalid browser dependency probe response")
    python = value["python"]
    if not isinstance(python, str) or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", python) is None:
        raise AgentTaskError("invalid browser dependency probe Python version")
    if any(not isinstance(value[key], bool) for key in _FLAGS):
        raise AgentTaskError("invalid browser dependency probe flags")
    expected = _report(python, (value["sdk"], value["readback_contract"], value["transfer_contract"],
                                value["playwright"]), transfer)
    if value != expected:
        raise AgentTaskError("browser dependency probe cannot establish native readiness")
    return expected
