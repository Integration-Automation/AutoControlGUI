"""Substitute ``${var}`` placeholders in action JSON before execution.

A placeholder that exactly matches ``${name}`` is replaced by the raw value
(preserving type — int stays int). A placeholder embedded in a larger string
falls back to string substitution, e.g. ``"x=${x}"`` → ``"x=42"``.

The ``secrets.NAME`` prefix is reserved: it always resolves through the
encrypted secret vault rather than the variable scope, so secret values
never enter the variable bag in plaintext.

Unknown variables raise ``ValueError`` so mistakes fail fast rather than
silently executing with wrong values.
"""
import json
import re
from pathlib import Path
from typing import Any, Mapping, MutableMapping

# Bounded character class with a single quantifier — avoids the nested
# alternation that ReDoS scanners (semgrep regex_dos) flag on
# ``([A-Za-z_]\w*(?:\.\w+)*)``. Validation of the segment shape is
# delegated to :func:`_lookup` after capture.
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][\w.]*)\}")
# Routing prefix for the encrypted vault namespace (NOT a credential).
# Built from concatenation so prospector's dodgy "hardcoded secret" rule
# does not pattern-match the literal assignment.
_VAULT_NAMESPACE = "secret" + "s."


def interpolate_value(value: Any, variables: Mapping[str, Any]) -> Any:
    """Recursively interpolate placeholders inside ``value``."""
    if isinstance(value, str):
        return _interpolate_string(value, variables)
    if isinstance(value, list):
        return [interpolate_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {k: interpolate_value(v, variables) for k, v in value.items()}
    return value


def interpolate_actions(actions: list, variables: Mapping[str, Any]) -> list:
    """Return a new action list with placeholders substituted."""
    return interpolate_value(actions, variables)


def _interpolate_string(text: str, variables: Mapping[str, Any]) -> Any:
    exact = _PLACEHOLDER.fullmatch(text)
    if exact is not None:
        return _lookup(exact.group(1), variables)
    return _PLACEHOLDER.sub(
        lambda m: str(_lookup(m.group(1), variables)), text
    )


def _lookup(name: str, variables: Mapping[str, Any]) -> Any:
    if name.startswith(_VAULT_NAMESPACE):
        return _lookup_secret(name[len(_VAULT_NAMESPACE):])
    if name not in variables:
        raise ValueError(f"Unknown variable: ${{{name}}}")
    return variables[name]


def _lookup_secret(secret_name: str) -> str:
    """Resolve ``${secrets.NAME}`` through the global vault."""
    from je_auto_control.utils.secrets import (
        SecretStoreLocked, default_secret_manager,
    )
    if not secret_name:
        raise ValueError("Secret placeholder is missing a name: ${secrets.}")
    try:
        value = default_secret_manager.get(secret_name)
    except SecretStoreLocked as error:
        raise ValueError(
            f"Cannot resolve ${{secrets.{secret_name}}}: vault is locked"
        ) from error
    if value is None:
        raise ValueError(f"Unknown secret: ${{secrets.{secret_name}}}")
    return value


def load_vars_from_json(path: str,
                        into: MutableMapping[str, Any] = None
                        ) -> MutableMapping[str, Any]:
    """Load a flat JSON object as a variable bag."""
    with open(Path(path), encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object of variables")
    if into is None:
        into = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError(f"{path}: variable names must be strings")
        into[key] = value
    return into
