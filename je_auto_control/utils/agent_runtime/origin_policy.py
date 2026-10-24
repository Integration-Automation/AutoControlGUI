"""Live origin path ceilings remain restrictive across accepted tasks, workers and service processes."""
from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, thaw

HEADER = "X-AutoControl-Agent-Origin"
_CURRENT: ContextVar[tuple[str, ...]] = ContextVar("agent_origin_policy", default=())
_PROVIDERS: ContextVar[tuple[Any, ...]] = ContextVar("agent_origin_providers", default=())


def _directory() -> Path:
    return Path.home() / ".je_auto_control" / "agent_origins"


def _path(identifier: str) -> Path:
    if not isinstance(identifier, str) or re.fullmatch(r"[0-9a-f]{32}", identifier) is None:
        raise AgentTaskError("invalid managed origin policy identity")
    return _directory() / (identifier + ".json")


class OriginWitness:
    """Private metadata describes a path ceiling, never a source of additional tool authority."""

    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.identifier = uuid.uuid4().hex
        self._active = True
        self.update(roots)

    def update(self, roots: tuple[Path, ...]) -> None:
        """Publish the latest roots before acknowledging a configured policy change."""
        from je_auto_control.utils.json_store.json_store import atomic_write_text
        path = _path(self.identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "active": self._active, "roots": [str(root) for root in roots]}
        try:
            atomic_write_text(path, json.dumps(payload))
            path.chmod(0o600)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        except OSError:
            path.unlink(missing_ok=True)
            raise

    def revoke(self) -> None:
        """Permanently revoke this witness; a late roots reply cannot reactivate it."""
        self._active = False
        self.update(())


def current_origin() -> str | None:
    """Return the caller's additional origin ceiling, if the trusted adapter supplied one."""
    origins = _current_identifiers()
    return ",".join(origins) if origins else None


def _current_identifiers() -> tuple[str, ...]:
    origins = list(_CURRENT.get())
    for policy in _PROVIDERS.get():
        identifier = policy.managed_origin()
        if identifier is not None and identifier not in origins:
            origins.append(identifier)
    if len(origins) > 16:
        raise AgentTaskError("too many nested managed origin ceilings")
    return tuple(origins)


@contextmanager
def source_policy_scope(policy: Any) -> Iterator[None]:
    """Carry a source policy through legacy tool wrappers, issuing metadata only for managed work."""
    providers = _PROVIDERS.get()
    if policy is not None and not any(item is policy for item in providers):
        providers += (policy,)
    token = _PROVIDERS.set(providers)
    try:
        yield
    finally:
        _PROVIDERS.reset(token)


@contextmanager
def origin_scope(identifier: str | None) -> Iterator[None]:
    """Bind an additional restrictive ceiling, without granting any identity or capability."""
    origins = list(_CURRENT.get())
    for value in identifier.split(",") if identifier is not None else ():
        _path(value)
        if value not in origins:
            origins.append(value)
    if len(origins) > 16:
        raise AgentTaskError("too many nested managed origin ceilings")
    token = _CURRENT.set(tuple(origins))
    try:
        yield
    finally:
        _CURRENT.reset(token)


def bind_origin(spec: AgentTaskSpec) -> AgentTaskSpec:
    """Pin the current ceiling in a newly accepted task without discarding prior ceilings."""
    current = _current_identifiers()
    if not current:
        return spec
    options = thaw(spec.options)
    origins = list(_identifiers(spec))
    for identifier in current:
        if identifier not in origins:
            origins.append(identifier)
    return replace(spec, options={**options, "origin_policies": origins})


def validate_origins(spec: AgentTaskSpec) -> None:
    """Recheck every source's current roots; missing/revoked/corrupt witnesses fail closed."""
    from je_auto_control.utils.path_guard.policy import PathPolicy
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    origins = set(_identifiers(spec))
    origins.update(_current_identifiers())
    for identifier in origins:
        value = _read(identifier)
        policy = PathPolicy(value["roots"], use_client_roots=True)
        try:
            for root in spec.roots:
                policy.validate(root, operation="live agent origin ceiling")
        except PathNotAllowedError as error:
            raise AgentTaskError("managed origin roots changed; review the task scope") from error


def review_origin_policies(spec: AgentTaskSpec) -> dict[str, Any]:
    """Snapshot current live ceilings and classify unavailable prior references for explicit review."""
    current = [_origin_record(identifier) for identifier in _current_identifiers()]
    known = {item["id"]: item for item in current}
    retained, unavailable = [], []
    source = _identifiers(spec)
    for identifier in source:
        try:
            state = known.get(identifier) or _origin_record(identifier)
        except AgentTaskError:
            unavailable.append(identifier)
        else:
            retained.append(state)
    return {"source": list(source), "current": current, "retained": retained, "unavailable": unavailable}


def _origin_record(identifier: str) -> dict:
    return {"id": identifier, "roots": _read(identifier)["roots"]}


def _identifiers(spec: AgentTaskSpec) -> tuple[str, ...]:
    identifiers = spec.options.get("origin_policies", ())
    if not isinstance(identifiers, (tuple, list)) or len(identifiers) > 16:
        raise AgentTaskError("task origin ceilings require at most sixteen explicit policies")
    for identifier in identifiers:
        _path(identifier)
    return tuple(identifiers)


def _read(identifier: str) -> dict:
    path = _path(identifier)
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError("invalid origin witness")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("version") != 1 or value.get("active") is not True:
            raise ValueError("revoked origin witness")
        roots = value.get("roots")
        if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
            raise ValueError("invalid origin roots")
        return value
    except (OSError, ValueError) as error:
        raise AgentTaskError("managed origin policy was revoked, removed or requires review") from error
