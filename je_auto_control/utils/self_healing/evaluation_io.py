"""Bounded local comparison manifests and shared JSON/HTML report export."""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.self_healing.evaluation import HealingComparison, evaluate_locators
from je_auto_control.utils.self_healing.evaluation_models import EvaluationSample, HealingEvaluationError, checked_box
from je_auto_control.utils.self_healing.frame_locators import TemplateFrameLocator


def _bounded_path(path: str | Path, policy: Optional[PathPolicy], *, parent: Optional[Path] = None) -> Path:
    candidate = validate_path(path, allowed_roots=[parent] if parent is not None else None)
    # pylint: disable-next=import-outside-toplevel  # reason: capture imports facade-backed executor adapters
    from je_auto_control.utils.action_journal.capture import _effective_path_policies
    for bound in _effective_path_policies(policy):
        candidate = bound.validate(candidate, operation="self-healing evaluation")
    return candidate


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise HealingEvaluationError("evaluation input exceeds its size limit")
    return payload


def _object(value: object, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise HealingEvaluationError("manifest object has missing or unsupported fields")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise HealingEvaluationError("manifest JSON keys must be unique")
        result[name] = value
    return result


@dataclass
class _AssetReader:
    parent: Path
    policy: Optional[PathPolicy]
    remaining: int = 64 * 1024 * 1024
    paths: list[Path] = field(default_factory=list)

    def read(self, value: object) -> bytes:
        """Read one confined asset while reducing the shared encoded-data budget."""
        if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
            raise HealingEvaluationError("assets must be relative file paths")
        path = _bounded_path(self.parent / value, self.policy, parent=self.parent)
        data = _read(path, min(self.remaining, 16 * 1024 * 1024))
        self.remaining -= len(data)
        self.paths.append(path)
        return data

    def check_paths(self) -> None:
        """Recheck current permissions on already loaded sample assets before using them."""
        for path in self.paths:
            _bounded_path(path, self.policy, parent=self.parent)


def _sample(value: object, reader: _AssetReader) -> EvaluationSample:
    fields = {"id", "frame", "expected_box", "expected_miss", "origin", "scale", "region", "run_id", "step_id"}
    row = _object(value, fields, {"id", "frame"})
    expected = checked_box(row["expected_box"], "expected_box") if row.get("expected_box") is not None else None
    region = checked_box(row["region"], "region") if row.get("region") is not None else None
    return EvaluationSample(row["id"], reader.read(row["frame"]), expected,
                            row.get("origin", (0, 0)), row.get("scale", 1), row.get("expected_miss", False),
                            region, row.get("run_id"), row.get("step_id"))


def _version(value: object, reader: _AssetReader) -> TemplateFrameLocator:
    row = _object(value, {"template", "threshold"}, {"template"})
    return TemplateFrameLocator(reader.read(row["template"]), row.get("threshold", 0.9))


def evaluate_healing_manifest(path: str | Path, *, path_policy: Optional[PathPolicy] = None,
                              observer: Optional[Callable[[int], None]] = None) -> HealingComparison:
    """Compare only local image versions; no implicit capture, input or network backend.

    Schema-v1 paths are relative to the manifest directory and cannot escape it,
    including through symlinks. Explicit and enclosing journal policies intersect.
    PNGs are bounded to 16 MiB each, manifest to 1 MiB, total pixels/files to
    64 MiB of encoded data. Observer exceptions propagate before further work.
    """
    samples, version_rows, reader = _load_samples_manifest(path, path_policy, observer, require_versions=True)
    versions = {}
    for name, row in version_rows.items():
        if observer is not None:
            observer(0)
        versions[name] = _version(row, reader)
    return evaluate_locators(samples, versions, observer=observer)


def _load_samples_manifest(path: str | Path, path_policy: Optional[PathPolicy],
                             observer: Optional[Callable[[int], None]], *, require_versions: bool = False
                             ) -> tuple[list[EvaluationSample], dict[str, Any], _AssetReader]:
    """Share bounded sample loading; candidate bundles supply their own frozen versions."""
    if observer is not None:
        observer(0)
    candidate = _bounded_path(path, path_policy)
    try:
        payload = json.loads(_read(candidate, 1024 * 1024), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as error:
        raise HealingEvaluationError("manifest must be UTF-8 JSON") from error
    required = {"schema_version", "samples", "versions"} if require_versions else {"schema_version", "samples"}
    body = _object(payload, {"schema_version", "samples", "versions"}, required)
    _check_manifest(body, require_versions=require_versions)
    samples = []
    reader = _AssetReader(candidate.parent, path_policy)
    for row in body["samples"]:
        if observer is not None:
            observer(0)
        samples.append(_sample(row, reader))
    return samples, body.get("versions", {}), reader


def _check_manifest(body: dict[str, Any], *, require_versions: bool = True) -> None:
    version = body["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise HealingEvaluationError("unsupported evaluation schema_version")
    sample_count = _sample_count(body["samples"])
    versions = body.get("versions", {})
    minimum = 1 if require_versions else 0
    if not isinstance(versions, dict) or not minimum <= len(versions) <= 32:
        raise HealingEvaluationError("manifest requires 1–32 versions and at most 10000 pairs")
    count = len(versions) if require_versions else 2
    if sample_count * count > 10000:
        raise HealingEvaluationError("manifest requires 1–32 versions and at most 10000 pairs")


def _sample_count(samples: object) -> int:
    if not isinstance(samples, list) or not 1 <= len(samples) <= 500:
        raise HealingEvaluationError("manifest requires 1–500 samples")
    return len(samples)


def write_healing_report(comparison: HealingComparison, path: str | Path, *,
                         path_policy: Optional[PathPolicy] = None) -> Path:
    """Atomically export sanitized JSON or a standalone escaped HTML comparison.

    Existing reports may be replaced. Source PNGs and templates are never written.
    """
    destination = _bounded_path(path, path_policy)
    if destination.suffix.lower() not in (".json", ".html"):
        raise HealingEvaluationError("report path must end in .json or .html")
    data = comparison.to_dict()
    rendered = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if destination.suffix.lower() == ".html":
        rendered = _html_report(comparison, rendered)
    atomic_write_text(destination, rendered)
    return destination


def _html_report(comparison: HealingComparison, rendered: str) -> str:
    rows = []
    for name, version in comparison.versions.items():
        ratio = version.accuracy
        latency = "unknown" if version.p95_ms is None else f"{version.p95_ms:.3f}"
        cells = (scrub_secret_text(name), f"{ratio.numerator}/{ratio.denominator}", str(version.unknown), latency)
        rows.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in cells) + "</tr>")
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>Locator comparison</title>"
            "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}"
            "td,th{padding:.6rem;text-align:left;border-bottom:1px solid #aaa}pre{white-space:pre-wrap}</style>"
            "<h1>Locator comparison</h1><p>Localization accuracy excludes unknown labels. "
            "Recovery requires a correct point and explicit operation verification. "
            "False positives are wrong detections among labelled predictions. Latencies are measured wall time.</p>"
            "<table><thead><tr><th>Version</th><th>Correct/labelled</th><th>Unknown</th>"
            "<th>p95 ms</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table><h2>Cases, provenance and populations</h2><pre>"
            + html.escape(rendered) + "</pre></html>")


def _evaluate_manifest_command(path: str) -> dict[str, object]:
    """Executor adapter shared by scripts, CLI and server action execution."""
    return evaluate_healing_manifest(path).to_dict()
