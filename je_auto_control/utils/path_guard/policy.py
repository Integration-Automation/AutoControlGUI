"""Opt-in confinement of file paths to a set of root directories.

:func:`~je_auto_control.utils.path_guard.path_guard.validate_path` bounds the
paths a CLI takes from ``argv`` and always has roots. A :class:`PathPolicy` is
the long-lived counterpart for a server: it is **off** until it is given roots,
its roots can change while it runs (an MCP client's ``roots/list``), and every
check names the operation that asked, so a refusal reads as "which argument of
which tool".

A path is canonicalised with ``os.path.realpath`` before it is compared, so
``..``, a symlink that points out of a root, another drive and a UNC share are
all judged by where they really lead.

Headless module: imports no PySide6.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable, Mapping, Optional, Tuple

from je_auto_control.utils.path_guard.path_guard import (
    PathNotAllowedError, _canonical, _is_within,
)

#: ``os.pathsep``-separated directories MCP tool file arguments must stay in.
MCP_PATH_ROOTS_ENV = "JE_AUTOCONTROL_MCP_PATH_ROOTS"
#: Truthy to also accept the roots the MCP client reports through ``roots/list``.
MCP_CLIENT_ROOTS_ENV = "JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


class PathPolicy:
    """Roots a path must resolve into; inactive until it has some.

    ``roots`` are fixed for the life of the policy. With ``use_client_roots``
    the directories passed to :meth:`set_client_roots` count as well, and the
    policy is active even before the first of them arrives — a path is then
    refused rather than let through while the roots are still unknown.
    """

    def __init__(self, roots: Iterable[os.PathLike[str] | str] = (), *,
                 use_client_roots: bool = False) -> None:
        self._static: Tuple[Path, ...] = tuple(_canonical(root) for root in roots)
        self._use_client_roots = bool(use_client_roots)
        self._client: Tuple[Path, ...] = ()
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "PathPolicy":
        """Build the policy the MCP environment variables describe.

        Neither variable set gives an inactive policy, which is the default.
        """
        source = os.environ if environ is None else environ
        roots = [entry.strip()
                 for entry in source.get(MCP_PATH_ROOTS_ENV, "").split(os.pathsep)
                 if entry.strip()]
        from_client = source.get(MCP_CLIENT_ROOTS_ENV, "").strip().lower() in _TRUTHY
        return cls(roots, use_client_roots=from_client)

    @property
    def enabled(self) -> bool:
        """Whether :meth:`validate` restricts anything."""
        return bool(self._static) or self._use_client_roots

    @property
    def use_client_roots(self) -> bool:
        """Whether roots reported by the client are honoured."""
        return self._use_client_roots

    def set_client_roots(self, roots: Iterable[os.PathLike[str] | str]) -> None:
        """Replace the client-reported roots; ignored unless they are honoured."""
        if not self._use_client_roots:
            return
        resolved = tuple(_canonical(root) for root in roots)
        with self._lock:
            self._client = resolved

    def roots(self) -> Tuple[Path, ...]:
        """Every root currently in force, configured ones first."""
        with self._lock:
            return self._static + self._client

    def validate(self, path: os.PathLike[str] | str, *, operation: str) -> Path:
        """Return ``path`` canonicalised, or raise :class:`PathNotAllowedError`.

        ``operation`` says what wanted the path and is quoted in the refusal.
        An inactive policy canonicalises and accepts. A path starting with
        ``~`` must be inside the roots both expanded and taken literally,
        because callers differ on whether they expand it.
        """
        text = os.fspath(path)
        if not text or "\x00" in text:
            raise PathNotAllowedError(f"{operation}: invalid path {text!r}")
        candidate = _canonical(text)
        if not self.enabled:
            return candidate
        roots = self.roots()
        readings = [candidate]
        if text.startswith("~"):
            readings.append(Path(os.path.realpath(text)))
        for reading in readings:
            if not any(_is_within(reading, root) for root in roots):
                raise PathNotAllowedError(
                    f"{operation}: {text!r} resolves to {reading}, outside the allowed "
                    f"roots ({', '.join(str(root) for root in roots) or 'none known yet'})")
        return candidate


__all__ = ["MCP_CLIENT_ROOTS_ENV", "MCP_PATH_ROOTS_ENV", "PathPolicy"]
