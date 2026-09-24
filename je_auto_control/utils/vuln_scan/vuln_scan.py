"""Match installed dependencies against OSV vulnerability advisories.

``utils/sbom`` *inventories* dependencies and ``utils/sarif`` *exports*
findings, but nothing in between ever **produced** a vulnerability finding —
there was no advisory matching at all. This closes that loop: given the SBOM's
``(ecosystem, name, version)`` components and an OSV advisory database, it
reports which packages are affected and bridges the results into the existing
SARIF exporter for GitHub / Azure DevOps code scanning.

The advisory database is *injected* as plain data (a list of OSV records), so
matching is fully offline and unit-testable; the live ``osv.dev`` query is a
separate, optional ``fetcher`` seam.

Version ordering is a pragmatic numeric comparison (release components compared
as integers, a pre-release suffix sorting before the final release). Remote/
git ranges and full CVSS-vector scoring are intentionally out of scope.

Pure standard library (``re``); imports no ``PySide6``.
"""
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.sarif import make_finding


# OSV / GHSA severity word -> SARIF level.
_SEVERITY_LEVELS = {
    "critical": "error", "high": "error", "moderate": "warning",
    "medium": "warning", "low": "note",
}

# purl type -> OSV ecosystem name.
_PURL_ECOSYSTEM = {
    "pypi": "PyPI", "npm": "npm", "cargo": "crates.io", "golang": "Go",
    "maven": "Maven", "gem": "RubyGems", "nuget": "NuGet",
    "composer": "Packagist",
}


_RELEASE_RE = re.compile(r"\d+(?:\.\d+)*")
_EPOCH_RE = re.compile(r"(\d+)!")
_PRE_LETTERS = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_PHASE_DEV, _PHASE_PRE, _PHASE_FINAL, _PHASE_POST = 0, 1, 2, 3


def _identifier(token: str) -> Tuple[int, Any]:
    """One pre-release identifier: numbers compare numerically, before words."""
    return (0, int(token)) if token.isdigit() else (1, token)


# Ends every PEP 440 pre-release key. It sorts below any identifier, so
# alpha < alpha.1 as SemVer requires, and above the (-2, N) that ends a
# ".devN" of that pre-release, so 1.0a1.dev1 < 1.0a1.
_PRE_FINAL = (-1, 0)


def _pep440_pre(tokens: List[str]) -> Tuple[Tuple[int, Any], ...]:
    """Identifiers of a PEP 440 pre-release such as ``a1`` or ``rc2.dev3``."""
    rest = tokens[1:]
    marker = _PRE_FINAL
    if "dev" in rest:
        at = rest.index("dev")
        dev = rest[at + 1:]
        marker = (-2, int(dev[0]) if dev and dev[0].isdigit() else 0)
        rest = rest[:at]
    return ((0, _PRE_LETTERS[tokens[0]]),) + tuple(_identifier(t) for t in rest) + (marker,)


def _suffix_key(suffix: str) -> Tuple[int, Tuple[Tuple[int, Any], ...]]:
    """``(phase, identifiers)`` for what follows the release numbers.

    PEP 440 phases rank dev < a/b/rc < final < post; anything else is a SemVer
    pre-release whose dot-separated identifiers compare as SemVer says.
    """
    tokens = re.findall(r"[a-z]+|\d+", suffix.lower())
    if not tokens:
        return _PHASE_FINAL, ()
    head = tokens[0]
    if head == "dev":
        return _PHASE_DEV, tuple(_identifier(t) for t in tokens[1:])
    if head in ("post", "rev", "r"):
        return _PHASE_POST, tuple(_identifier(t) for t in tokens[1:])
    if head in _PRE_LETTERS:
        return _PHASE_PRE, _pep440_pre(tokens)
    return _PHASE_PRE, tuple(_identifier(t) for t in re.split(r"[.]", suffix.lower()) if t)


def version_key(version: str) -> Tuple[Tuple[int, ...], int, Tuple[Tuple[int, Any], ...]]:
    """Return a sortable key for a version string: (release, phase, identifiers).

    Trailing zeros do not count (``2.0`` == ``2.0.0``), build metadata and
    PEP 440 local versions (``+cu118``) are ignored, and pre-releases -- PEP
    440 ``rc1`` / ``.dev1`` or SemVer ``-alpha.10`` -- sort before the release.
    The release tuple starts with the PEP 440 epoch (0 when absent).
    """
    text = str(version).strip().lstrip("vV").split("+", 1)[0]
    epoch_match = _EPOCH_RE.match(text)
    epoch = int(epoch_match.group(1)) if epoch_match else 0
    if epoch_match:
        text = text[epoch_match.end():]
    match = _RELEASE_RE.match(text)
    release = tuple(int(n) for n in match.group(0).split(".")) if match else ()
    while release and release[-1] == 0:
        release = release[:-1]
    phase, identifiers = _suffix_key(text[match.end():] if match else text)
    # The PEP 440 epoch leads the release numbers: 1!1.0 is above every 2.x.
    return ((epoch,) + release, phase, identifiers)


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name).strip().lower())


def _ecosystem_from_purl(purl: str) -> str:
    match = re.match(r"pkg:([^/]+)/", purl or "")
    if not match:
        return ""
    kind = match.group(1).lower()
    return _PURL_ECOSYSTEM.get(kind, match.group(1))


def _sorted_events(events: Sequence[Mapping[str, Any]]) -> List[Tuple[str, str]]:
    parsed: List[Tuple[str, str]] = []
    for event in events:
        for kind in ("introduced", "fixed", "last_affected"):
            if kind in event:
                parsed.append((kind, str(event[kind])))
                break
    return sorted(parsed, key=lambda item: (
        version_key(item[1]), 0 if item[0] == "introduced" else 1))


def is_affected(version: str, osv_range: Mapping[str, Any]) -> bool:
    """Return ``True`` if ``version`` falls inside one OSV range's events."""
    if osv_range.get("type") == "GIT":
        return False
    target = version_key(version)
    affected = False
    for kind, bound in _sorted_events(osv_range.get("events", [])):
        if kind == "introduced":
            affected = bound == "0" or target >= version_key(bound)
        elif kind == "fixed" and target >= version_key(bound):
            affected = False
        elif kind == "last_affected" and target > version_key(bound):
            affected = False
    return affected


def _package_matches(package: Mapping[str, Any], ecosystem: str, name: str) -> bool:
    if _normalize_name(package.get("name", "")) != _normalize_name(name):
        return False
    package_eco = str(package.get("ecosystem", ""))
    return not (ecosystem and package_eco and package_eco.lower() != ecosystem.lower())


def _affected_entry_hits(entry: Mapping[str, Any], ecosystem: str,
                         name: str, version: str) -> bool:
    if not _package_matches(entry.get("package", {}), ecosystem, name):
        return False
    if version in [str(v) for v in entry.get("versions", [])]:
        return True
    return any(is_affected(version, rng) for rng in entry.get("ranges", []))


def _advisory_hits(advisory: Mapping[str, Any], ecosystem: str,
                   name: str, version: str) -> bool:
    return any(_affected_entry_hits(entry, ecosystem, name, version)
               for entry in advisory.get("affected", []))


def _fix_after(version: str, osv_range: Mapping[str, Any]) -> Optional[str]:
    """The first ``fixed`` bound above ``version`` in one range, if any."""
    target = version_key(version)
    for kind, bound in _sorted_events(osv_range.get("events", [])):
        if kind == "fixed" and version_key(bound) > target:
            return bound
    return None


def _first_fixed(advisory: Mapping[str, Any], ecosystem: str, name: str,
                 version: str) -> Optional[str]:
    """The fix for this package at this version.

    It used to be the first ``fixed`` of any entry, so a finding for one
    package could name another package's fix, or an earlier range's.
    """
    for entry in advisory.get("affected", []):
        if not _package_matches(entry.get("package", {}), ecosystem, name):
            continue
        for osv_range in entry.get("ranges", []):
            fixed = _fix_after(version, osv_range)
            if fixed is not None:
                return fixed
    return None


def _severity_level(advisory: Mapping[str, Any]) -> str:
    raw = str(advisory.get("database_specific", {}).get("severity", "")).lower()
    return _SEVERITY_LEVELS.get(raw, "warning")


def _to_finding(advisory: Mapping[str, Any], ecosystem: str, name: str,
                version: str) -> Dict[str, Any]:
    return {
        "id": str(advisory.get("id", "OSV-UNKNOWN")),
        "package": name,
        "version": version,
        "summary": str(advisory.get("summary", "")),
        "severity": _severity_level(advisory),
        "fixed": _first_fixed(advisory, ecosystem, name, version),
        "aliases": list(advisory.get("aliases", [])),
    }


def match_package(ecosystem: str, name: str, version: str,
                  advisories: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return a finding per advisory that affects ``name``@``version``."""
    return [_to_finding(advisory, ecosystem, name, version) for advisory in advisories
            if _advisory_hits(advisory, ecosystem, name, version)]


def scan_components(components: Sequence[Mapping[str, Any]],
                    advisories: Optional[Sequence[Mapping[str, Any]]] = None, *,
                    fetcher: Optional[Callable[[str, str], Sequence]] = None
                    ) -> List[Dict[str, Any]]:
    """Scan SBOM ``components`` against ``advisories`` (and an optional fetcher)."""
    base = list(advisories or [])
    findings: List[Dict[str, Any]] = []
    for component in components:
        name = str(component.get("name", ""))
        version = str(component.get("version", ""))
        ecosystem = str(component.get("ecosystem", "")) or \
            _ecosystem_from_purl(component.get("purl", ""))
        records = base + list(fetcher(ecosystem, name) or []) if fetcher else base
        findings.extend(match_package(ecosystem, name, version, records))
    return findings


def findings_to_sarif(findings: Sequence[Mapping[str, Any]]
                      ) -> List[Dict[str, Any]]:
    """Convert vulnerability findings into SARIF-ready normalized findings."""
    results = []
    for finding in findings:
        summary = finding.get("summary") or finding["id"]
        message = f"{finding['package']} {finding['version']}: {summary}"
        if finding.get("fixed"):
            message += f" (fixed in {finding['fixed']})"
        results.append(make_finding(finding["id"], message,
                                    level=finding.get("severity", "warning")))
    return results
