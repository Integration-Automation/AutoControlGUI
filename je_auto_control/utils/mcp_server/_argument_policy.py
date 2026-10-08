"""Opt-in limits on what a tool call's arguments may name on this machine.

Three schema annotations drive it, so the rule lives next to the argument it
governs instead of in a list of tool names:

* ``"format": "path"`` — the string is a file or directory the tool will open.
  With roots configured it must resolve inside one of them, and the tool is
  handed the canonical path that was checked, so ``~`` and a relative path
  cannot mean one thing to the check and another to the handler.
* ``"format": "value-ref"`` — the value holds ``env://`` / ``file://``
  references (``ac_resolve_ref`` / ``ac_resolve_refs``). ``file://`` targets
  follow the same roots; ``env://`` names follow the allowlist.
* ``"format": "path-or-other"`` — the string is a path on some calls and
  something else on others: a URL (``ac_open_path``), a file extension
  (``ac_file_association``), text to look for (``ac_act_in_view``), text
  typed into a dialog (``ac_handle_file_dialog``). It is held to the roots
  when it *is* a path -- when it looks like an absolute one or names
  something that exists (:func:`looks_like_path`), and a ``file:`` URL by
  the file it names -- and left alone otherwise. It is checked, never
  rewritten: the same string may be the text a caller meant.

A command line (``ac_launch_process`` ``argv``, ``ac_shell`` ``command``) is
deliberately not annotated. Refusing the arguments that read as paths would
confine nothing -- the program decides what its arguments mean, and can be
told the same thing another way -- so the roots make no claim about it.

Nothing is restricted until an operator configures it: see
:class:`~je_auto_control.utils.path_guard.policy.PathPolicy` for the roots and
:func:`~je_auto_control.utils.secret_ref.secret_ref.env_allowlist_from_env`.
"""
import os
import re
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.secret_ref.secret_ref import (
    RefResolver, env_allowlist_from_env,
)

PATH_FORMAT = "path"
VALUE_REF_FORMAT = "value-ref"
PATH_OR_OTHER_FORMAT = "path-or-other"

_FILE_SCHEME = "file:"
# A drive path with its separator. ``Q: text`` is not taken for a path; a bare
# ``C:`` or a drive-relative ``C:name`` is one only if it exists.
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_ABSOLUTE_PREFIXES = ("/", "\\", "~")


def file_url_path(value: str) -> Optional[str]:
    """The filesystem path a ``file:`` URL names; ``None`` for anything else."""
    if not value[:len(_FILE_SCHEME)].lower() == _FILE_SCHEME:
        return None
    parts = urlsplit(value)
    path = url2pathname(parts.path) if parts.path else unquote(parts.netloc)
    if parts.path and parts.netloc and parts.netloc.lower() != "localhost":
        return f"\\\\{parts.netloc}{path}" if os.name == "nt" else f"//{parts.netloc}{path}"
    return path


def looks_like_path(value: str) -> bool:
    """Whether a sometimes-a-path string is a path this time.

    True for a ``file:`` URL, for anything shaped like an absolute path on
    either platform (``/x``, ``\\x``, ``~``, ``C:\\x``, a UNC share) whether or
    not it exists, and for any other string that names something that does
    exist relative to the server's working directory (``..``, ``notes.txt``).
    A URL, an extension or a word that names nothing is not a path.
    """
    if not value:
        return False
    if file_url_path(value) is not None or value.startswith(_ABSOLUTE_PREFIXES):
        return True
    if _DRIVE_PATH.match(value):
        return True
    try:
        return os.path.lexists(value)
    except (OSError, ValueError):
        return False  # not a name any filesystem accepts


class ArgumentPolicy:
    """The path roots and ``env://`` allowlist one MCP server enforces."""

    def __init__(self, path_policy: Optional[PathPolicy] = None,
                 env_allowlist: Optional[Tuple[str, ...]] = None) -> None:
        self.path_policy = path_policy if path_policy is not None else PathPolicy()
        self.env_allowlist = env_allowlist

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "ArgumentPolicy":
        """Build the policy the process environment describes (default: none)."""
        return cls(PathPolicy.from_env(environ), env_allowlist_from_env(environ))

    @property
    def enabled(self) -> bool:
        """Whether :meth:`apply` can refuse or rewrite anything."""
        return self.path_policy.enabled or self.env_allowlist is not None

    def apply(self, tool_name: str, schema: Dict[str, Any],
              arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``arguments`` with every path canonicalised, or raise.

        Raises :class:`~je_auto_control.utils.path_guard.PathNotAllowedError`
        for a path outside the roots and
        :class:`~je_auto_control.utils.secret_ref.SecretRefError` for a
        refused reference — both :class:`AutoControlException`.
        """
        if not self.enabled:
            return arguments
        return self._walk(schema, arguments, f"{tool_name} $")

    def _walk(self, schema: Any, value: Any, where: str) -> Any:
        if not isinstance(schema, dict):
            return value
        marker = schema.get("format")
        if marker == VALUE_REF_FORMAT:
            RefResolver(env_allowlist=self.env_allowlist,
                        path_policy=self.path_policy).check_all(value)
            return value
        if marker == PATH_FORMAT and isinstance(value, str):
            return self._confine(value, where)
        if marker == PATH_OR_OTHER_FORMAT and isinstance(value, str):
            self._confine_if_path(value, where)
            return value
        if isinstance(value, dict):
            declared = schema.get("properties") or {}
            extra = schema.get("additionalProperties")
            return {key: self._walk(declared.get(key, extra), item, f"{where}.{key}")
                    for key, item in value.items()}
        if isinstance(value, list):
            return [self._walk(schema.get("items"), item, f"{where}[{index}]")
                    for index, item in enumerate(value)]
        return value

    def _confine(self, value: str, where: str) -> str:
        if not value or not self.path_policy.enabled:
            return value  # an empty path is the handler's "not given"
        return str(self.path_policy.validate(value, operation=where))

    def _confine_if_path(self, value: str, where: str) -> None:
        """Hold ``value`` to the roots when it is a path; say nothing otherwise."""
        if not self.path_policy.enabled or not looks_like_path(value):
            return
        named = file_url_path(value)
        self.path_policy.validate(value if named is None else named, operation=where)


__all__ = ["ArgumentPolicy", "PATH_FORMAT", "PATH_OR_OTHER_FORMAT", "VALUE_REF_FORMAT",
           "file_url_path", "looks_like_path"]
