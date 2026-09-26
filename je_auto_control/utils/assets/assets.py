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
import functools
import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.json_store import SharedJsonDict

ENV_VAR = "JE_AUTOCONTROL_ENV"
DEFAULT_ENV = "default"
TYPE_TEXT = "text"
TYPE_INT = "int"
TYPE_BOOL = "bool"
TYPE_CREDENTIAL = "credential"
_TYPES = (TYPE_TEXT, TYPE_INT, TYPE_BOOL, TYPE_CREDENTIAL)


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


_TRUE_WORDS = ("1", "true", "yes", "on")
_FALSE_WORDS = ("0", "false", "no", "off", "")


def _as_int(value: Any) -> int:
    """An int, refusing bools and fractions: 3.7 was stored as 3 and True as 1."""
    if isinstance(value, bool):
        raise ValueError("a bool is not an int asset")
    if isinstance(value, float) and not (math.isfinite(value) and value.is_integer()):
        raise ValueError(f"{value!r} is not a whole number")
    try:
        return int(value)
    except OverflowError as error:
        raise ValueError(str(error)) from error


def _as_flag(value: Any) -> bool:
    """A bool from a known spelling: "enabled" was silently False."""
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS or word in _FALSE_WORDS:
            return word in _TRUE_WORDS
        raise ValueError(f"{value!r} is not a bool asset; use true / false")
    return bool(value)


def _coerce(value: Any, type_name: str) -> Any:
    if type_name == TYPE_INT:
        return _as_int(value)
    if type_name == TYPE_BOOL:
        return _as_flag(value)
    return value if type_name == TYPE_CREDENTIAL else str(value)


class AssetStore:
    """A typed, environment-scoped key/value store backed by optional JSON."""

    def __init__(self, db_path: Optional[str] = None, *,
                 secret_resolver: Optional[Callable[[str], Any]] = None
                 ) -> None:
        """``secret_resolver(name)`` resolves ``credential`` references lazily."""
        # Re-read and locked per change, so processes sharing the file do
        # not overwrite each other's assets.
        self._state = SharedJsonDict(db_path)
        self._resolver = secret_resolver

    def set(self, name: str, value: Any, *, asset_type: str = TYPE_TEXT,
            environment: str = DEFAULT_ENV) -> None:
        """Store ``value`` for ``name`` under ``environment`` with a type tag.

        An unknown type, or a value the type cannot read (``"eighty"`` as an
        ``int``), raises ``ValueError`` here -- it used to be stored and then
        fail on every later read.
        """
        if asset_type not in _TYPES:
            raise ValueError(f"unknown asset type {asset_type!r}; expected one of {_TYPES}")
        try:
            _coerce(value, asset_type)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{value!r} is not a valid {asset_type} asset") from error
        record = {"type": asset_type, "value": value}
        self._state.update(
            lambda data: data.setdefault(environment, {}).__setitem__(name, record))

    def _lookup(self, name: str, environment: str,
                fallback_to_default: bool) -> Optional[Dict[str, Any]]:
        data = self._state.read()
        record = data.get(environment, {}).get(name)
        if record is None and fallback_to_default and environment != DEFAULT_ENV:
            record = data.get(DEFAULT_ENV, {}).get(name)
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
        return self._state.update(
            lambda data: data.get(environment, {}).pop(name, None) is not None)

    def list(self, *, environment: Optional[str] = None) -> List[Asset]:
        """List assets, optionally restricted to one ``environment``."""
        data = self._state.read()
        envs = [environment] if environment else list(data)
        return [
            Asset(name, str(rec["type"]), env, rec["value"])
            for env in envs
            for name, rec in data.get(env, {}).items()
        ]


@functools.lru_cache(maxsize=1)
def _process_store() -> AssetStore:
    return AssetStore(None)


def asset_store(db: Optional[str] = None) -> AssetStore:
    """The store in ``db`` or, without ``db``, the one this process shares.

    Each command built a fresh in-memory store, so without ``db`` a value
    set by ``AC_set_asset`` was gone by the next ``AC_get_asset``.
    """
    return AssetStore(db) if db else _process_store()


def store_set(name: str, value: Any, *, asset_type: str = TYPE_TEXT,
              environment: str = DEFAULT_ENV,
              db: Optional[str] = None) -> Dict[str, Any]:
    """Set an asset and return a result dict (shared by executor/MCP layers)."""
    asset_store(db).set(name, value, asset_type=asset_type,
                       environment=environment)
    return {"ok": True, "name": name, "environment": environment}


def store_get(name: str, *, environment: str = DEFAULT_ENV,
              db: Optional[str] = None) -> Dict[str, Any]:
    """Get an asset as a result dict (credential value stays a reference)."""
    asset = asset_store(db).get(name, environment=environment)
    return {"name": asset.name, "type": asset.type, "value": asset.value}


def store_list(*, environment: Optional[str] = None,
               db: Optional[str] = None) -> Dict[str, Any]:
    """List assets as a result dict of ``{name, type, environment}`` (no values)."""
    assets = asset_store(db).list(environment=environment)
    return {"assets": [{"name": a.name, "type": a.type,
                        "environment": a.environment} for a in assets]}
