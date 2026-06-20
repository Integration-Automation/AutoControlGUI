"""Typed, environment-scoped assets — the orchestrator "Assets / lockers" pillar.

Flows need centrally-managed config values that differ by environment
(dev/staging/prod) and carry a type (text/int/bool/credential). The secret vault
covers secrets only and config-sync moves whole blobs; neither offers a typed,
per-environment named lookup. ``AssetStore`` fills that: values are stored under
an environment, read back with type coercion, and ``credential`` assets hold a
*reference* (a secret name) that :meth:`AssetStore.resolve` turns into the real
value through an injected resolver — so the secret never lands in a plain
``get``/executor record.

JSON-backed (or in-memory); pure standard library; imports no ``PySide6``.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ENV_VAR = "JE_AUTOCONTROL_ENV"
DEFAULT_ENV = "default"
TYPE_TEXT = "text"
TYPE_INT = "int"
TYPE_BOOL = "bool"
TYPE_CREDENTIAL = "credential"


@dataclass(frozen=True)
class Asset:
    """A stored asset record (``value`` is a secret *name* when credential)."""

    name: str
    type: str
    environment: str
    value: Any


@dataclass(frozen=True)
class AssetValue:
    """A read asset with its declared type and coerced (non-secret) value."""

    name: str
    type: str
    value: Any


def active_environment() -> str:
    """Return the active environment from ``JE_AUTOCONTROL_ENV`` (or default)."""
    return os.environ.get(ENV_VAR, DEFAULT_ENV)


def _coerce(value: Any, type_name: str) -> Any:
    if type_name == TYPE_INT:
        return int(value)
    if type_name == TYPE_BOOL:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    return value if type_name == TYPE_CREDENTIAL else str(value)


class AssetStore:
    """A typed, environment-scoped key/value store backed by optional JSON."""

    def __init__(self, db_path: Optional[str] = None, *,
                 secret_resolver: Optional[Callable[[str], Any]] = None
                 ) -> None:
        """``secret_resolver(name)`` resolves ``credential`` references lazily."""
        self._path = Path(db_path) if db_path else None
        self._resolver = secret_resolver
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _flush(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def set(self, name: str, value: Any, *, type: str = TYPE_TEXT,
            environment: str = DEFAULT_ENV) -> None:
        """Store ``value`` for ``name`` under ``environment`` with a type tag."""
        self._data.setdefault(environment, {})[name] = {
            "type": type, "value": value}
        self._flush()

    def _lookup(self, name: str, environment: str,
                fallback_to_default: bool) -> Optional[Dict[str, Any]]:
        record = self._data.get(environment, {}).get(name)
        if record is None and fallback_to_default and environment != DEFAULT_ENV:
            record = self._data.get(DEFAULT_ENV, {}).get(name)
        return record

    def get(self, name: str, *, environment: str = DEFAULT_ENV,
            fallback_to_default: bool = True) -> AssetValue:
        """Return the typed asset (credential values stay as a reference)."""
        record = self._lookup(name, environment, fallback_to_default)
        if record is None:
            raise KeyError(f"asset {name!r} not found for {environment!r}")
        type_name = str(record["type"])
        return AssetValue(name, type_name,
                          _coerce(record["value"], type_name))

    def resolve(self, name: str, *, environment: str = DEFAULT_ENV) -> Any:
        """Like :meth:`get` but resolves a ``credential`` to its real value."""
        asset = self.get(name, environment=environment)
        if asset.type != TYPE_CREDENTIAL:
            return asset.value
        if self._resolver is None:
            raise RuntimeError("no secret_resolver configured for credentials")
        return self._resolver(str(asset.value))

    def delete(self, name: str, *, environment: str = DEFAULT_ENV) -> bool:
        """Delete an asset; return whether it existed."""
        removed = self._data.get(environment, {}).pop(name, None) is not None
        if removed:
            self._flush()
        return removed

    def list(self, *, environment: Optional[str] = None) -> List[Asset]:
        """List assets, optionally restricted to one ``environment``."""
        envs = [environment] if environment else list(self._data)
        return [
            Asset(name, str(rec["type"]), env, rec["value"])
            for env in envs
            for name, rec in self._data.get(env, {}).items()
        ]


def store_set(name: str, value: Any, *, type: str = TYPE_TEXT,
              environment: str = DEFAULT_ENV,
              db: Optional[str] = None) -> Dict[str, Any]:
    """Set an asset and return a result dict (shared by executor/MCP layers)."""
    AssetStore(db).set(name, value, type=type, environment=environment)
    return {"ok": True, "name": name, "environment": environment}


def store_get(name: str, *, environment: str = DEFAULT_ENV,
              db: Optional[str] = None) -> Dict[str, Any]:
    """Get an asset as a result dict (credential value stays a reference)."""
    asset = AssetStore(db).get(name, environment=environment)
    return {"name": asset.name, "type": asset.type, "value": asset.value}


def store_list(*, environment: Optional[str] = None,
               db: Optional[str] = None) -> Dict[str, Any]:
    """List assets as a result dict of ``{name, type, environment}`` (no values)."""
    assets = AssetStore(db).list(environment=environment)
    return {"assets": [{"name": a.name, "type": a.type,
                        "environment": a.environment} for a in assets]}
