"""Open a file with its default app, or a URL in the default browser.

The framework can launch a literal executable (``start_exe`` / ``shell_process``),
but not the single most common "hand off to another app" RPA step: open ``report.pdf``
with whatever app is registered for it, ``print`` a document, or open a URL in the
default browser. ``shell_open`` adds that, routed per-OS to ``os.startfile`` /
``open`` / ``xdg-open`` / ``webbrowser``.

:func:`plan_open` is a pure planner — it classifies the target (URL vs file path),
validates it (URL scheme allowlist; ``realpath`` for files) and returns the
dispatch descriptor, fully unit-testable. :func:`open_path` runs the plan through
an injectable ``opener`` sink (the real OS call by default), so the dispatch logic
is testable without launching anything. Imports no ``PySide6``.
"""
import os
import re
import sys
from typing import Any, Callable, Dict, Optional

# URL schemes we will hand to the browser / OS — the safety allowlist.
_URL_SCHEMES = frozenset({"http", "https", "ftp", "file", "mailto", "tel"})
_SCHEME_AUTHORITY = re.compile(r"([a-zA-Z][a-zA-Z0-9+.\-]+)://")
_SCHEME_OPAQUE = re.compile(r"(mailto|tel):", re.IGNORECASE)

# A plan dispatcher: maps a plan dict to the real open call → bool.
Opener = Callable[[Dict[str, Any]], bool]


def _scheme(target: str) -> Optional[str]:
    """Return the URL scheme of ``target`` (e.g. ``https``), or None for a path.

    Requires ``scheme://`` (so a Windows drive ``C:\\`` is not a scheme) or a known
    opaque scheme (``mailto:`` / ``tel:``).
    """
    match = _SCHEME_AUTHORITY.match(target) or _SCHEME_OPAQUE.match(target)
    return match.group(1).lower() if match else None


def _file_backend() -> str:
    if sys.platform.startswith("win"):
        return "startfile"
    if sys.platform == "darwin":
        return "open"
    return "xdg-open"


def plan_open(target: str, *, verb: str = "open") -> Dict[str, Any]:
    """Classify ``target`` and return how to open it (pure, no side effect).

    Returns ``{kind, target, backend, verb}`` (plus ``scheme`` for URLs). Raises
    ``ValueError`` for an empty target or a URL whose scheme isn't allow-listed.
    """
    text = str(target).strip()
    if not text:
        raise ValueError("target is empty")
    scheme = _scheme(text)
    if scheme is not None:
        if scheme not in _URL_SCHEMES:
            raise ValueError(f"unsupported URL scheme: {scheme!r}")
        return {"kind": "url", "scheme": scheme, "target": text,
                "backend": "webbrowser", "verb": verb}
    path = os.path.realpath(os.path.expanduser(text))
    return {"kind": "file", "target": path, "backend": _file_backend(),
            "verb": verb}


def _default_opener(plan: Dict[str, Any]) -> bool:
    backend, target = plan["backend"], plan["target"]
    if backend == "webbrowser":
        import webbrowser
        return bool(webbrowser.open(target))
    if backend == "startfile":
        if not sys.platform.startswith("win"):
            raise RuntimeError("startfile is only supported on Windows")
        # file path is from the allow-listed plan; os.startfile is not a shell
        os.startfile(target, plan.get("verb") or "open")  # noqa: S606  # nosec B606  # nosemgrep
        return True
    import subprocess  # nosec B404  # reason: argv list, no shell
    # fixed backend + argv list, no shell — injection-safe
    subprocess.Popen([backend, target])  # nosec B603  # nosemgrep
    return True


def open_path(target: str, *, verb: str = "open",
              opener: Optional[Opener] = None) -> bool:
    """Open ``target`` (file → default app / verb; URL → default browser).

    Pass an ``opener`` ``plan -> bool`` to intercept the dispatch (e.g. in tests);
    the default runs the real OS call. Returns True on success.
    """
    plan = plan_open(target, verb=verb)
    dispatch = opener if opener is not None else _default_opener
    return bool(dispatch(plan))
