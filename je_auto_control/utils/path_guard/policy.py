"""Explicit filesystem/environment policies shared by remote entry points."""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterable, Iterator, Optional

from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError

MCP_ROOTS_ENV = 'JE_AUTOCONTROL_MCP_ROOTS'
MCP_ENV_ALLOWLIST = 'JE_AUTOCONTROL_MCP_ALLOWED_ENV'


def _canonical(raw: str | Path) -> Path:
    text = str(raw)
    if not text or '\x00' in text:
        raise PathNotAllowedError('filesystem path is empty or contains a NUL')
    try:
        return Path(text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise PathNotAllowedError(f'cannot resolve path {text!r}') from error


class PathPolicy:
    """Bound paths to explicit roots; None preserves unrestricted local access.

    Additional root sets narrow the policy by intersection, never union.
    An empty root list denies filesystem access. Environment names are exact:
    None is unrestricted; an empty allowlist denies all environment references.
    """

    def __init__(self, roots: Optional[Iterable[str | Path]] = None, *,
                 allowed_env: Optional[Iterable[str]] = None) -> None:
        self.roots = None if roots is None else tuple(_canonical(root) for root in roots)
        self.allowed_env = None if allowed_env is None else frozenset(allowed_env)

    @classmethod
    def for_mcp(cls) -> PathPolicy:
        """Read deployment configuration; remote env refs are denied by default."""
        raw = os.environ.get(MCP_ROOTS_ENV)
        roots = None if raw is None else [p for p in raw.split(os.pathsep) if p.strip()]
        allowed = os.environ.get(MCP_ENV_ALLOWLIST, '')
        return cls(roots, allowed_env=[p.strip() for p in allowed.split(',') if p.strip()])

    def restrict(self, roots: Iterable[str | Path]) -> PathPolicy:
        """Return the intersection with client roots without changing this policy."""
        incoming = tuple(_canonical(root) for root in roots)
        if self.roots is None:
            return PathPolicy(incoming, allowed_env=self.allowed_env)
        shared = []
        for current in self.roots:
            for root in incoming:
                if root.is_relative_to(current):
                    shared.append(root)
                elif current.is_relative_to(root):
                    shared.append(current)
        return PathPolicy(shared, allowed_env=self.allowed_env)

    def validate(self, path: str, *, operation: str) -> Path:
        """Resolve a read/write destination and reject realpath/symlink escapes."""
        if operation not in {'read', 'write'}:
            raise PathNotAllowedError(f'unknown filesystem operation {operation!r}')
        if not path or '\x00' in path:
            raise PathNotAllowedError('filesystem path is empty or contains a NUL')
        candidate = Path(path).expanduser()
        if not candidate.is_absolute() and self.roots:
            candidate = self.roots[0] / candidate
        resolved = _canonical(candidate)
        if self.roots is not None and not any(resolved.is_relative_to(root) for root in self.roots):
            raise PathNotAllowedError(f'path is outside the allowed roots: {path!r}')
        return resolved

    def validate_env(self, name: str) -> None:
        """Reject an environment reference not present in the exact allowlist."""
        if self.allowed_env is not None and name not in self.allowed_env:
            raise PathNotAllowedError(f'environment reference is not allowed: {name!r}')


_ACTIVE_POLICY: ContextVar[Optional[PathPolicy]] = ContextVar('file_boundary_policy', default=None)


def current_path_policy() -> Optional[PathPolicy]:
    """Return the policy bound to the current remote call, if any."""
    return _ACTIVE_POLICY.get()


def scoped_path(path: str | Path, *, operation: str) -> Path:
    """Validate effective file access when a remote policy is active."""
    policy = current_path_policy()
    return Path(path) if policy is None else policy.validate(str(path), operation=operation)


@contextmanager
def path_policy_scope(policy: Optional[PathPolicy]) -> Iterator[None]:
    """Apply a policy to reference resolution for one call and restore its parent."""
    token = _ACTIVE_POLICY.set(policy)
    try:
        yield
    finally:
        _ACTIVE_POLICY.reset(token)
