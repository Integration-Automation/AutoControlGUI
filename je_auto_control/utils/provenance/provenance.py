"""Build and verify SLSA build provenance (in-toto v1 statements).

The framework can sign action files (HMAC) and inventory dependencies (SBOM),
but it could not attest *what was produced by which build* — the SLSA
provenance attestation that binds artifact digests to build metadata. This adds
an in-toto v1 Statement carrying a SLSA v1 provenance predicate over file
sha256 digests, plus a verifier that re-hashes the artifacts.

Pure standard library (``hashlib`` + ``json`` + ``os``); fully offline; imports
no ``PySide6``. DSSE signing of the statement is intentionally left as an
optional later layer.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
_PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
_CHUNK = 65536


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def subject_for(path: str, *, name: Optional[str] = None) -> Dict[str, Any]:
    """Return an in-toto subject (name + sha256 digest) for a file."""
    return {"name": name or os.path.basename(path),
            "digest": {"sha256": _sha256_file(path)}}


def subject_for_bytes(name: str, data: bytes) -> Dict[str, Any]:
    """Return an in-toto subject for in-memory ``data``."""
    return {"name": name, "digest": {"sha256": hashlib.sha256(data).hexdigest()}}


def build_provenance(subjects: Sequence[Mapping[str, Any]], *,
                     build_type: str = "https://je-auto-control/buildtype/v1",
                     builder_id: str = "je_auto_control",
                     external_parameters: Optional[Mapping[str, Any]] = None,
                     metadata: Optional[Mapping[str, Any]] = None
                     ) -> Dict[str, Any]:
    """Build an in-toto v1 statement with a SLSA v1 provenance predicate."""
    meta = metadata or {}
    return {
        "_type": _STATEMENT_TYPE,
        "subject": [dict(subject) for subject in subjects],
        "predicateType": _PREDICATE_TYPE,
        "predicate": {
            "buildDefinition": {
                "buildType": build_type,
                "externalParameters": dict(external_parameters or {}),
                "internalParameters": {},
                "resolvedDependencies": [],
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {
                    "invocationId": meta.get("invocation_id", ""),
                    "startedOn": meta.get("started_on", ""),
                    "finishedOn": meta.get("finished_on", ""),
                },
                "byproducts": [],
            },
        },
    }


def write_provenance(statement: Mapping[str, Any], path: str) -> str:
    """Write a provenance statement to ``path``; return the resolved path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(statement, indent=2), encoding="utf-8")
    return str(out.resolve())


def verify_provenance(statement: Mapping[str, Any],
                      files: Mapping[str, str]) -> List[Dict[str, Any]]:
    """Re-hash ``files`` (name->path) and return digest mismatches."""
    expected = {subject["name"]: subject.get("digest", {}).get("sha256")
                for subject in statement.get("subject", [])}
    mismatches: List[Dict[str, Any]] = []
    for name, path in files.items():
        actual = _sha256_file(path)
        if expected.get(name) != actual:
            mismatches.append({"name": name, "expected": expected.get(name),
                               "actual": actual})
    return mismatches
