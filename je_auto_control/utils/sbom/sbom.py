"""Generate a CycloneDX Software Bill of Materials for an automation project.

Supply-chain regulation (EU Cyber Resilience Act, US EO 14028) increasingly
requires a machine-readable SBOM listing every dependency that ships with a
product. This module walks the installed Python distributions (and,
optionally, the dependency closure of one package) and emits a **CycloneDX
1.6** JSON document — the de-facto SBOM standard — without any third-party
dependency.

Pure standard library (``importlib.metadata`` + ``json``); imports no
``PySide6``.
"""
import json
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_SCHEMA = "https://cyclonedx.org/schema/bom-1.6.schema.json"
_BOM_FORMAT = "CycloneDX"
_SPEC_VERSION = "1.6"


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name}@{version}"


def _component(dist: "metadata.Distribution") -> Dict[str, Any]:
    name = dist.metadata["Name"] or "unknown"
    version = dist.version or "0"
    component: Dict[str, Any] = {
        "type": "library", "name": name, "version": version,
        "purl": _purl(name, version),
    }
    # `dist.metadata` is an `email.message.Message`: it answers `get`,
    # but is not declared as a mapping.
    license_name = dist.metadata.get("License")  # type: ignore[attr-defined]  # reason: Message.get
    if license_name and license_name != "UNKNOWN":
        component["licenses"] = [{"license": {"name": license_name}}]
    return component


def _iter_distributions(root: Optional[str]):
    """Yield distributions: all installed, or the closure of ``root``."""
    if root is None:
        yield from metadata.distributions()
        return
    seen: Set[str] = set()
    queue = [root]
    while queue:
        name = queue.pop()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        yield dist
        for req in (dist.requires or []):
            queue.append(_requirement_name(req))


def _requirement_name(requirement: str) -> str:
    """Extract the bare distribution name from a requirement string."""
    token = requirement.strip()
    for sep in (" ", ";", "=", "<", ">", "!", "~", "(", "["):
        token = token.split(sep, 1)[0]
    return token.strip()


def build_sbom(root: Optional[str] = "je_auto_control", *,
               extra_components: Optional[List[Dict[str, Any]]] = None
               ) -> Dict[str, Any]:
    """Return a CycloneDX 1.6 SBOM as a dict.

    ``root`` limits output to that distribution's dependency closure; pass
    ``None`` to inventory every installed distribution. ``extra_components``
    are appended verbatim (e.g. action-file entries).
    """
    components = []
    for dist in _iter_distributions(root):
        try:
            components.append(_component(dist))
        except (KeyError, AttributeError):
            continue
    components.extend(extra_components or [])
    components.sort(key=lambda c: (c.get("name", ""), c.get("version", "")))
    return {
        "$schema": _SCHEMA,
        "bomFormat": _BOM_FORMAT,
        "specVersion": _SPEC_VERSION,
        "version": 1,
        "metadata": {"tools": [{"name": "je_auto_control", "vendor": "JE-Chen"}]},
        "components": components,
    }


def write_sbom(path: str = "sbom.cdx.json",
               root: Optional[str] = "je_auto_control",
               **kwargs: Any) -> str:
    """Write a CycloneDX SBOM to ``path``; return the resolved path."""
    sbom = build_sbom(root, **kwargs)
    target = Path(path)
    target.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    return str(target.resolve())
