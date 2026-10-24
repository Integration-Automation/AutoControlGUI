"""Durable target profiles, live controls and explicit dependency diagnostics separate from native evidence."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached, thaw
from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile, reviewed_tools
from je_auto_control.utils.agent_runtime.target_factory import build_target
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.rbac.authorization import current_authorization

OPERATIONS = ("register", "get", "disable", "enable", "probe")
_PROBE_FIELDS = frozenset({"status", "reason", "python", "sdk", "readback_contract", "transfer_contract",
                            "playwright", "browser_launch", "native_evidence"})
_PROBE_STATUSES = frozenset({"python_dependencies_ready", "dependency_missing", "incompatible", "unknown",
                              "not_supported"})


class AgentTargetProfiles:
    """Only host management can publish or enable resources; ordinary callers receive inert summaries."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._profiles: dict[str, AgentTargetProfile] = {}
        self._enabled: dict[str, bool] = {}
        self._last_probes: dict[str, dict] = {}
        with runtime.store.connection() as connection:
            rows = connection.execute("SELECT * FROM agent_target_profiles ORDER BY created,name LIMIT 101").fetchall()
            controls = connection.execute("SELECT * FROM agent_target_controls").fetchall()
        if len(rows) > 100:
            raise AgentTaskError("stored target profile count exceeds its bound")
        for row in rows:
            profile = AgentTargetProfile.from_dict(json.loads(row["config"]))
            if profile.name != row["name"] or profile.digest != row["digest"] or profile.name in runtime._targets:
                raise AgentTaskError("stored target profile integrity or target identity changed")
            self._profiles[profile.name] = profile
            runtime._targets[profile.name] = build_target(profile)
        for row in controls:
            if row["enabled"] not in (0, 1):
                raise AgentTaskError("stored target enable control is invalid")
            self._enabled[row["name"]] = bool(row["enabled"])

    def control(self, operation: str, request: Mapping | None = None) -> dict:
        """Register an immutable profile or explicitly change target availability with host authority."""
        identity = current_authorization()
        if identity is not None and not identity.allows("manage_hosts"):
            raise AgentTaskError("target configuration requires host management")
        value = detached({} if request is None else request)
        if operation not in OPERATIONS or not isinstance(value, dict):
            raise AgentTaskError("invalid target profile operation")
        if operation == "probe":
            return self._probe(value)
        with self._runtime._mutex:
            if operation == "register":
                return self._register(value)
            name = self._request_name(value)
            if operation in {"disable", "enable"}:
                self._toggle(name, operation == "enable")
            return self._details(name)

    def _probe(self, value: dict) -> dict:
        with self._runtime._mutex:
            name = self._request_name(value)
            adapter = self._runtime._targets[name]
        probe = getattr(adapter, "probe", None)
        raw = detached(probe() if callable(probe) else {"status": "not_supported",
                                                        "native_evidence": "not_recorded"})
        if not isinstance(raw, dict) or not isinstance(raw.get("status"), str) or raw["status"] not in _PROBE_STATUSES:
            raise AgentTaskError("invalid target dependency probe response")
        if raw.get("native_evidence") != "not_recorded":
            raise AgentTaskError("dependency probes cannot establish native evidence")
        report = {key: item for key, item in raw.items() if key in _PROBE_FIELDS}
        with self._runtime._mutex:
            self._last_probes[name] = {**report, "checked_at": time.time()}
            details = self._details(name)
            details["probe"] = detached(self._last_probes[name])
            return details

    def _request_name(self, value: dict) -> str:
        if set(value) != {"name"} or not isinstance(value["name"], str):
            raise AgentTaskError("target operation requires one configured name")
        if value["name"] not in self._runtime._targets:
            raise AgentTaskError("target operation requires one configured name")
        return value["name"]

    def _register(self, value: dict) -> dict:
        profile = AgentTargetProfile.from_dict(value)
        name = profile.name
        if name in self._runtime._targets or name in self._enabled:
            raise AgentTaskError("target profile already exists; its identity is immutable")
        if len(self._profiles) >= 100:
            raise AgentTaskError("at most one hundred target profiles may be configured")
        adapter = build_target(profile)
        identity = current_authorization()
        with self._runtime.store.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_target_profiles VALUES (?,?,?,?,?)", (
                name, json.dumps(profile.to_dict()), profile.digest, time.time(),
                identity.user_id if identity is not None else "local"))
            connection.execute("INSERT INTO agent_target_controls VALUES (?,1)", (name,))
        self._profiles[name], self._enabled[name] = profile, True
        self._runtime._targets[name] = adapter
        return self._details(name)

    def _toggle(self, name: str, enabled: bool) -> None:
        with self._runtime.store.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_target_controls VALUES (?,?) ON CONFLICT(name) "
                               "DO UPDATE SET enabled=excluded.enabled", (name, int(enabled)))
        self._enabled[name] = enabled
        if not enabled:
            for task_id in list(self._runtime._leases):
                if self._runtime.store.get(task_id)["spec"]["target"] == name:
                    self._runtime.pause(task_id)

    def bind(self, spec: AgentTaskSpec) -> AgentTaskSpec:
        """Pin the real host identity and reject forged or widened task configuration."""
        self.check(spec, require_pin=False)
        profile = self._profiles.get(spec.target)
        if profile is None:
            return spec
        options = {**thaw(spec.options), "target_profile": {"name": profile.name, "digest": profile.digest}}
        return replace(spec, options=options)

    def check(self, spec: AgentTaskSpec, *, require_pin: bool = True) -> None:
        """Recheck enablement and the task's immutable resource identity at every dispatch checkpoint."""
        if not self._enabled.get(spec.target, True):
            raise AgentTaskError("target is disabled; host review is required")
        profile = self._profiles.get(spec.target)
        pin = spec.options.get("target_profile")
        if profile is None:
            if pin is not None:
                raise AgentTaskError("task target profile is no longer configured")
            return
        expected = {"name": profile.name, "digest": profile.digest}
        if pin != expected and (pin is not None or require_pin):
            raise AgentTaskError("task target profile identity changed or its pin is invalid")
        profile.check(spec)

    def describe(self) -> dict:
        """List resource names and declared adapter support without native probes or sensitive configuration."""
        with self._runtime._mutex:
            return {"targets": [self._summary(name) for name in sorted(self._runtime._targets)]}

    def _summary(self, name: str) -> dict:
        profile = self._profiles.get(name)
        kind = profile.kind if profile is not None else {"local-desktop": "desktop", "local-files": "files"}.get(
            name, "injected")
        tools = list(profile.allowed_tools) if profile is not None else sorted(
            reviewed_tools(kind)) if kind in {"desktop", "files", "browser"} else []
        result: dict[str, Any] = {"name": name, "kind": kind, "enabled": self._enabled.get(name, True),
                "declared_tools": tools,
                "managed_profile": profile is not None, "readiness": "not_probed", "native_evidence": "not_recorded",
                "digest": profile.digest if profile is not None else None}
        # pylint: disable-next=protected-access  # reason: no custom adapter descriptor runs during passive diagnostics
        adapter = self._runtime._targets[name]
        # pylint: disable-next=unidiomatic-typecheck  # reason: only the built-in proxy's passive property is trusted here
        declared = type(adapter) is NativeDesktopTarget and adapter.supports_readonly_completion
        result["readonly_completion"] = {"contract": 1, "status": "not_probed"} if declared else {
            "status": "not_supported"}
        if name in self._last_probes:
            result["last_probe"] = detached(self._last_probes[name])
        return result

    def _details(self, name: str) -> dict:
        profile = self._profiles.get(name)
        result = self._summary(name)
        if profile is not None:
            result["profile"] = profile.to_dict()
        return result
