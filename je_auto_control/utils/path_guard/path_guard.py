"""Canonicalise and bound filesystem paths that arrive from a CLI argument.

The ``python -m je_auto_control...`` entry points take output/input paths from
``argv``. A mistaken — or generated — argument such as ``../../etc/passwd``
would otherwise be handed straight to ``write_text``/``mkdir``. Every such
path goes through :func:`validate_path` first: it is canonicalised with
``os.path.realpath`` (so ``..`` and symlinks are resolved before the check)
and must land inside one of the allowed roots.

The default roots are the current working directory, the user's home and the
system temp directory — the places an operator actually exports to. Set
``AUTOCONTROL_ALLOWED_PATH_ROOTS`` (``os.pathsep``-separated) to add more, for
example a mounted volume in a container.

Headless module: imports no PySide6.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException

ALLOWED_ROOTS_ENV = "AUTOCONTROL_ALLOWED_PATH_ROOTS"


class PathNotAllowedError(AutoControlException):
    """A supplied path is malformed or resolves outside the allowed roots."""


def default_allowed_roots() -> List[Path]:
    """Return the roots a CLI path may resolve into, extras from env first."""
    roots: List[Path] = []
    for entry in os.environ.get(ALLOWED_ROOTS_ENV, "").split(os.pathsep):
        if entry.strip():
            roots.append(_canonical(entry.strip()))
    roots.append(_canonical(Path.cwd()))
    roots.append(_canonical(Path.home()))
    roots.append(_canonical(tempfile.gettempdir()))
    return roots


def validate_path(raw: os.PathLike | str, *,
                  allowed_roots: Optional[Iterable[os.PathLike | str]] = None,
                  allowed_suffixes: Optional[Sequence[str]] = None,
                  must_exist: bool = False) -> Path:
    """Return ``raw`` canonicalised, or raise :class:`PathNotAllowedError`.

    ``allowed_suffixes`` is matched case-insensitively against the final
    suffix. ``must_exist`` additionally requires the resolved path to be
    present on disk.
    """
    text = os.fspath(raw)
    if not text or "\x00" in text:
        raise PathNotAllowedError(f"invalid path: {text!r}")
    candidate = _canonical(text)
    _check_suffix(candidate, allowed_suffixes)
    roots = default_allowed_roots() if allowed_roots is None \
        else [_canonical(root) for root in allowed_roots]
    if not any(_is_within(candidate, root) for root in roots):
        raise PathNotAllowedError(
            f"{candidate} is outside the allowed roots "
            f"({', '.join(str(root) for root in roots)}); "
            f"set {ALLOWED_ROOTS_ENV} to permit it")
    if must_exist and not candidate.exists():
        raise PathNotAllowedError(f"{candidate} does not exist")
    return candidate


# --- internals ----------------------------------------------------

def _canonical(value: os.PathLike | str) -> Path:
    return Path(os.path.realpath(Path(value).expanduser()))


def _check_suffix(candidate: Path,
                  allowed_suffixes: Optional[Sequence[str]]) -> None:
    if not allowed_suffixes:
        return
    wanted = {suffix.lower() for suffix in allowed_suffixes}
    if candidate.suffix.lower() not in wanted:
        raise PathNotAllowedError(
            f"{candidate.name} does not end in {' / '.join(sorted(wanted))}")


def _is_within(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents
