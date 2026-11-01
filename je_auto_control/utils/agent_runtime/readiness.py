"""Passive readiness of the desktop, presence source, devices, browser and models; never a grant or evidence.

Each area reports one of ``STATES``. Nothing here probes a native API, connects
to a device, launches a helper, imports an optional dependency or asks for a
permission, so no area can be ``measured``: only a recorded native acceptance
proves that, and ``native_evidence`` is therefore always ``not_recorded``.
"""
from __future__ import annotations

import importlib.util
import shutil
from typing import Any, Callable

from je_auto_control.wrapper.capabilities import BackendContext, CapabilityStatus, probe_capabilities

STATES = ("unsupported", "missing_dependency", "unauthorized", "not_probed", "not_recorded", "measured")

# A passive capability observation never becomes "measured": "available" only
# says a backend is present, so on this desktop it is still "not_recorded".
_FROM_CAPABILITY = {
    "available": "not_recorded", "needs_permission": "unauthorized", "paused": "unauthorized",
    "revoked": "unauthorized", "needs_dependency": "missing_dependency", "unsupported": "unsupported",
    "unverified": "not_probed", "failed": "not_probed",
}


def _entry(area: str, state: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"area": area, "state": state, "detail": detail, "native_evidence": "not_recorded", **extra}


def _capability(area: str, status: CapabilityStatus) -> dict[str, Any]:
    return _entry(area, _FROM_CAPABILITY[status.state], status.reason, observed=status.state,
                  backend=status.backend, recovery=status.recovery)


def _presence(platform: str, display_server: str) -> dict[str, Any]:
    if platform == "win32":
        return _entry("presence_source", "not_probed",
                      "a Windows session source exists; it is read only once a managed task binds it")
    return _entry("presence_source", "unsupported",
                  f"no trusted human-activity source for {platform}/{display_server}; shared-desktop input "
                  "stays refused", display_server=display_server)


def _executable(area: str, name: str, purpose: str, which: Callable[[str], Any]) -> dict[str, Any]:
    if which(name) is None:
        return _entry(area, "missing_dependency", f"{name} is not on PATH; {purpose}")
    return _entry(area, "not_probed", f"{name} is on PATH; no device was contacted")


def _package(area: str, module: str, purpose: str, find: Callable[[str], Any]) -> dict[str, Any]:
    if find(module) is None:
        return _entry(area, "missing_dependency", f"{module} is not installed; {purpose}")
    return _entry(area, "not_probed", f"{module} is installed; nothing was launched")


def agent_runtime_readiness(context: BackendContext | None = None, *,
                            which: Callable[[str], Any] = shutil.which,
                            find_spec: Callable[[str], Any] = importlib.util.find_spec) -> dict[str, Any]:
    """Report what each managed-task area needs, from environment and installed files only."""
    context = context or BackendContext.current()
    snapshot = probe_capabilities(context)
    areas = [
        _capability("desktop_input", snapshot.input),
        _capability("desktop_capture", snapshot.capture),
        _presence(context.platform, snapshot.display_server),
        _executable("android_transport", "adb", "Android targets need the platform tools", which),
        _entry("android_managed_control", "unsupported",
               "no device-side command provider is installed; managed Android input stays refused"),
        _entry("ios_managed_control", "unsupported",
               "no WebDriverAgent device adapter is implemented; managed iOS input stays refused"),
        _package("browser", "je_web_runner", "browser targets use WebRunner", find_spec),
        _entry("local_model", "not_probed",
               "each task names its own installed Ollama model and loopback endpoint; none is checked here"),
    ]
    return {"platform": context.platform, "display_server": snapshot.display_server, "passive": True,
            "states": list(STATES), "areas": areas}
