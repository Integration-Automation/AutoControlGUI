"""Resolve URI-scheme value references (``env://`` / ``file://`` / ``secret://``).

``script_vars.interpolate`` hardcodes a single indirection (``${secrets.NAME}``
→ vault) and ``AssetStore`` credential references are vault-name-only. There was
no general, pluggable read-time indirection — the modern config pattern of
storing a *pointer* (``env://TOKEN``, ``file://./token``, ``secret://api-key``)
rather than the value. This adds that resolver.

Pure standard library (``os`` / ``re``); imports no ``PySide6``. The env reader,
secret resolver, and base directory are injectable, so resolution is safe and
deterministic in CI.
"""
import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException

_REF_RE = re.compile(r"^(env|file|secret)://(.*)$", re.DOTALL)

EnvReader = Mapping[str, str]
SecretResolver = Callable[[str], Optional[str]]


class SecretRefError(AutoControlException):
    """A value reference could not be resolved."""


def is_ref(value: Any) -> bool:
    """Whether ``value`` is an ``env://`` / ``file://`` / ``secret://`` ref."""
    return isinstance(value, str) and _REF_RE.match(value) is not None


def _default_secret(name: str) -> str:
    from je_auto_control.utils.governance import default_broker
    token = default_broker.lease(name, ttl=1.0)
    try:
        return default_broker.redeem(token)
    except AutoControlException as error:
        raise SecretRefError(f"secret {name!r} not resolvable: {error}") from error
    finally:
        default_broker.revoke(token)


class RefResolver:
    """Resolve value references via injectable env / secret / file backends."""

    def __init__(self, *, env: Optional[EnvReader] = None,
                 secret_resolver: Optional[SecretResolver] = None,
                 base_dir: Optional[str] = None) -> None:
        self._env = env
        self._secret_resolver = secret_resolver
        self._base_dir = base_dir

    def resolve(self, ref: str) -> str:
        """Resolve a single reference string to its value."""
        match = _REF_RE.match(ref or "")
        if match is None:
            raise SecretRefError(f"not a value reference: {ref!r}")
        scheme, target = match.group(1), match.group(2)
        if scheme == "env":
            return self._resolve_env(target)
        if scheme == "file":
            return self._resolve_file(target)
        return self._resolve_secret(target)

    def resolve_all(self, obj: Any) -> Any:
        """Recursively resolve every reference in a nested structure."""
        if isinstance(obj, dict):
            return {key: self.resolve_all(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self.resolve_all(item) for item in obj]
        if is_ref(obj):
            return self.resolve(obj)
        return obj

    def _resolve_env(self, name: str) -> str:
        source = self._env if self._env is not None else os.environ
        if name not in source:
            raise SecretRefError(f"env var {name!r} is not set")
        return source[name]

    def _resolve_file(self, path: str) -> str:
        resolved = os.path.realpath(path)
        if self._base_dir is not None:
            base = os.path.realpath(self._base_dir)
            if os.path.commonpath([base, resolved]) != base:
                raise SecretRefError(f"path escapes base dir: {path!r}")
        try:
            return Path(resolved).read_text(encoding="utf-8")
        except OSError as error:
            raise SecretRefError(f"cannot read {path!r}: {error}") from error

    def _resolve_secret(self, name: str) -> str:
        resolver = self._secret_resolver
        if resolver is None:
            return _default_secret(name)
        value = resolver(name)
        if value is None:
            raise SecretRefError(f"resolver returned no value for {name!r}")
        return value


def resolve_ref(ref: str, *, env: Optional[EnvReader] = None,
                secret_resolver: Optional[SecretResolver] = None,
                base_dir: Optional[str] = None) -> str:
    """Resolve a single ``env://`` / ``file://`` / ``secret://`` reference."""
    return RefResolver(env=env, secret_resolver=secret_resolver,
                       base_dir=base_dir).resolve(ref)


def resolve_refs_in(obj: Any, *, env: Optional[EnvReader] = None,
                    secret_resolver: Optional[SecretResolver] = None,
                    base_dir: Optional[str] = None) -> Any:
    """Recursively resolve every reference within a nested structure."""
    return RefResolver(env=env, secret_resolver=secret_resolver,
                       base_dir=base_dir).resolve_all(obj)
