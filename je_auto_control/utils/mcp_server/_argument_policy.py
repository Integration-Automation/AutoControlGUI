"""Opt-in limits on what a tool call's arguments may name on this machine.

Two schema annotations drive it, so the rule lives next to the argument it
governs instead of in a list of tool names:

* ``"format": "path"`` — the string is a file or directory the tool will open.
  With roots configured it must resolve inside one of them, and the tool is
  handed the canonical path that was checked, so ``~`` and a relative path
  cannot mean one thing to the check and another to the handler.
* ``"format": "value-ref"`` — the value holds ``env://`` / ``file://``
  references (``ac_resolve_ref`` / ``ac_resolve_refs``). ``file://`` targets
  follow the same roots; ``env://`` names follow the allowlist.

Nothing is restricted until an operator configures it: see
:class:`~je_auto_control.utils.path_guard.policy.PathPolicy` for the roots and
:func:`~je_auto_control.utils.secret_ref.secret_ref.env_allowlist_from_env`.
"""
from typing import Any, Dict, Mapping, Optional, Tuple

from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.secret_ref.secret_ref import (
    RefResolver, env_allowlist_from_env,
)

PATH_FORMAT = "path"
VALUE_REF_FORMAT = "value-ref"


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


__all__ = ["ArgumentPolicy", "PATH_FORMAT", "VALUE_REF_FORMAT"]
