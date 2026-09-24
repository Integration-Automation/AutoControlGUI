"""Evaluate dependency licenses against an allow / deny policy.

``utils/sbom`` records each component's license *name* but never judges it, so
a copyleft or otherwise-disallowed license could ship unnoticed. This adds the
policy gate: normalize the SBOM's license strings to SPDX ids, evaluate them
against an allowlist / denylist (with a built-in strong-copyleft set), and emit
violations that bridge into the existing SARIF exporter — the license-compliance
lane beside the OSV vulnerability lane.

Pure standard library (``re``); imports no ``PySide6``.
"""
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from je_auto_control.utils.sarif import make_finding

# Strong/network copyleft SPDX ids most policies want to flag.
DEFAULT_COPYLEFT = frozenset({
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "LGPL-2.1-only", "LGPL-3.0-only",
    "LGPL-3.0-or-later", "MPL-2.0", "EPL-2.0", "CDDL-1.0",
})

# Canonical SPDX id -> the loose names that should normalize to it. Inverted
# below so each SPDX id literal appears exactly once (no duplicated literals).
_ALIAS_GROUPS = {
    "MIT": ("mit license", "the mit license", "mit"),
    "Apache-2.0": ("apache 2.0", "apache-2", "apache 2", "apache2",
                   "apache software license", "apache license 2.0"),
    "BSD-3-Clause": ("bsd", "bsd license", "new bsd license"),
    "GPL-2.0-only": ("gplv2",),
    "GPL-3.0-only": ("gplv3", "gnu gplv3"),
    "LGPL-3.0-only": ("lgplv3",),
    "MPL-2.0": ("mpl 2.0",),
    "ISC": ("isc license",),
}
_ALIASES = {alias: spdx for spdx, names in _ALIAS_GROUPS.items()
            for alias in names}

# An operator only counts between whitespace or parentheses: "\b" also
# matched at the hyphens of "GPL-2.0-or-later", cutting it into three tokens.
_TOKEN_SPLIT = re.compile(r"((?<![^\s()])(?:OR|AND|WITH)(?![^\s()])|[()])", re.IGNORECASE)
_OPERATORS = ("OR", "AND", "WITH", "(", ")")
# GPL / LGPL / AGPL ids, whose "+" and deprecated bare forms have SPDX names.
_GNU_ID = re.compile(r"(?i)((?:A|L)?GPL-\d\.\d)(\+|-only|-or-later)?")


def _gnu_id(text: str) -> Optional[str]:
    """``GPL-2.0+`` -> ``GPL-2.0-or-later``; deprecated ``GPL-2.0`` -> ``-only``."""
    match = _GNU_ID.fullmatch(text)
    if match is None:
        return None
    later = (match.group(2) or "").lower() in ("+", "-or-later")
    return f"{match.group(1).upper()}-{'or-later' if later else 'only'}"


def normalize_spdx(raw: str) -> str:
    """Normalize a single license token to a canonical SPDX id (best effort)."""
    text = str(raw).strip()
    if not text:
        return ""
    alias = _ALIASES.get(text.lower())
    if alias:
        return alias
    lowered = text.lower()
    for suffix in (" license", " licence"):
        if lowered.endswith(suffix):
            return text[:-len(suffix)].strip()
    return _gnu_id(text) or text.rstrip("+")


# A parsed expression: ("id", spdx) or ("and" / "or", [children]).
_Node = Tuple[str, Union[str, List[Any]]]


class _ExpressionParser:
    """Recursive descent over an SPDX expression: OR binds loosest, then AND.

    The old check switched to "any" whenever the text held " or ", so
    ``(MIT OR Apache-2.0) AND Proprietary`` passed an MIT-only allowlist.
    """

    def __init__(self, text: str) -> None:
        self._tokens = [part.strip() for part in _TOKEN_SPLIT.split(text) if part.strip()]
        self._pos = 0

    def parse(self) -> _Node:
        node = self._either()
        if self._pos != len(self._tokens):
            raise ValueError("unexpected token in license expression")
        return node

    def _peek(self) -> Optional[str]:
        if self._pos >= len(self._tokens):
            return None
        return self._tokens[self._pos].upper()

    def _take(self) -> str:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _either(self) -> _Node:
        children = [self._both()]
        while self._peek() == "OR":
            self._take()
            children.append(self._both())
        return ("or", children) if len(children) > 1 else children[0]

    def _both(self) -> _Node:
        children = [self._atom()]
        while self._peek() == "AND":
            self._take()
            children.append(self._atom())
        return ("and", children) if len(children) > 1 else children[0]

    def _atom(self) -> _Node:
        if self._peek() == "(":
            self._take()
            node = self._either()
            if self._peek() != ")":
                raise ValueError("unbalanced parenthesis in license expression")
            self._take()
            return node
        if self._peek() in (None,) + _OPERATORS:
            raise ValueError("missing license id in license expression")
        license_id = normalize_spdx(self._take())
        if self._peek() == "WITH":
            # An exception only relaxes the license it is attached to; the
            # verdict is the license's.
            self._take()
            if self._peek() in (None,) + _OPERATORS:
                raise ValueError("missing exception after WITH")
            self._take()
        return ("id", license_id)


def _key_set(values: Optional[Sequence[str]]) -> Set[str]:
    """SPDX ids compare case-insensitively: ``gpl-3.0-only`` is ``GPL-3.0-only``."""
    return {normalize_spdx(value).lower() for value in values} if values else set()


def _satisfied(node: _Node, allow: Optional[Set[str]], deny: Set[str]) -> bool:
    kind, value = node
    if isinstance(value, str):  # an ("id", spdx) leaf
        key = value.lower()
        return key not in deny and (allow is None or key in allow)
    results = [_satisfied(child, allow, deny) for child in value]
    return any(results) if kind == "or" else all(results)


def evaluate_license(license_str: str, *,
                     allow: Optional[Sequence[str]] = None,
                     deny: Optional[Sequence[str]] = None) -> str:
    """Return ``allowed`` / ``denied`` / ``unknown`` for a license string.

    The expression is parsed: ``OR`` needs one acceptable choice, ``AND``
    needs all of them, and ``WITH`` is judged by its license. An empty or
    malformed expression is ``unknown``.
    """
    text = str(license_str or "")
    if not text.strip():
        return "unknown"
    try:
        tree = _ExpressionParser(text).parse()
    except ValueError:
        return "unknown"
    allow_set = None if allow is None else _key_set(allow)
    return "allowed" if _satisfied(tree, allow_set, _key_set(deny)) else "denied"


def _component_license(component: Mapping[str, Any]) -> str:
    for entry in component.get("licenses", []):
        if "expression" in entry:
            return str(entry["expression"])
        license_obj = entry.get("license", {})
        name = license_obj.get("id") or license_obj.get("name")
        if name:
            return str(name)
    return ""


def evaluate_sbom(components: Sequence[Mapping[str, Any]], *,
                  allow: Optional[Sequence[str]] = None,
                  deny: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Return a violation per component whose license is not ``allowed``."""
    violations: List[Dict[str, Any]] = []
    for component in components:
        license_str = _component_license(component)
        status = evaluate_license(license_str, allow=allow, deny=deny)
        if status != "allowed":
            violations.append({
                "name": str(component.get("name", "")),
                "version": str(component.get("version", "")),
                "license": license_str,
                "status": status,
            })
    return violations


def license_findings_to_sarif(violations: Sequence[Mapping[str, Any]]
                              ) -> List[Dict[str, Any]]:
    """Convert license violations into SARIF-ready normalized findings."""
    findings = []
    for violation in violations:
        level = "error" if violation["status"] == "denied" else "warning"
        shown = violation["license"] or "unknown"
        message = (f"{violation['name']} {violation['version']}: license "
                   f"'{shown}' is {violation['status']}")
        findings.append(make_finding(
            f"license/{violation['name']}", message, level=level))
    return findings
