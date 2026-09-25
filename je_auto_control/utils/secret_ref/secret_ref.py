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



_DRIVE_URL_PATH = re.compile(r"^/[A-Za-z]:[/\\]")


def _is_within(base: str, resolved: str) -> bool:
    """Whether ``resolved`` is ``base`` or below it; other drives are not."""
    try:
        return os.path.commonpath([base, resolved]) == base
    except ValueError:  # different drives, or absolute vs relative
        return False

class SecretRefError(AutoControlException):
    """A value reference could not be resolved."""


def is_ref(value: Any) -> bool:
    """Whether ``value`` is an ``env://`` / ``file://`` / ``secret://`` ref."""
    return isinstance(value, str) and _REF_RE.match(value) is not None


def refuse_secret_refs(obj: Any) -> None:
    """Raise ``SecretRefError`` if ``obj`` holds a ``secret://`` reference anywhere.

    For surfaces whose results are recorded -- the executor and MCP: the
    credential broker's contract is that secret values never enter those
    records, and ``AC_resolve_ref`` returned them there as ``{value}``.
    """
    if isinstance(obj, dict):
        for value in obj.values():
            refuse_secret_refs(value)
    elif isinstance(obj, list):
        for item in obj:
            refuse_secret_refs(item)
    elif isinstance(obj, str) and obj.startswith("secret://"):
        raise SecretRefError(
            "secret:// values are not returned into executor records or MCP results; "
            "reference ${secrets.NAME} in the step that needs the value")


def _default_secret(name: str) -> str:
    from je_auto_control.utils.governance import default_broker
    token = default_broker.lease(name, ttl=1.0)
    try:
        return default_broker.redeem(token)
    # LookupError: a resolver that looks names up in a mapping misses with KeyError.
    except (AutoControlException, LookupError) as error:
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
        if not isinstance(ref, str):
            raise SecretRefError(f"not a value reference: {ref!r}")
        match = _REF_RE.match(ref)
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
        if _DRIVE_URL_PATH.match(path):
            path = path[1:]  # file:///C:/x names C:/x, not the drive-relative /C:/x
        if "\0" in path:
            raise SecretRefError(f"path contains a NUL byte: {path!r}")
        if self._base_dir is None:
            resolved = os.path.realpath(path)
        else:
            # A relative ref is relative to base_dir: it used to resolve
            # against the working directory and then fail the check below.
            base = os.path.realpath(self._base_dir)
            resolved = os.path.realpath(os.path.join(base, path))
            if not _is_within(base, resolved):
                raise SecretRefError(f"path escapes base dir: {path!r}")
        try:
            return Path(resolved).read_text(encoding="utf-8")
        # ValueError: an embedded NUL, or a file that is not UTF-8.
        except (OSError, ValueError) as error:
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
