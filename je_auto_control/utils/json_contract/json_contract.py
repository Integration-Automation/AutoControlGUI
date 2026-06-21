"""Match, diff and snapshot JSON payloads (contract / golden-master testing).

``json_schema`` validates a value against an authored schema and ``jsonpath``
extracts values, but nothing matched two JSON payloads with relaxed rules
(type-only, partial, ignore volatile paths) or diffed them path-by-path for
contract / snapshot tests. This adds that layer; it composes with
``json_schema`` (shape) and ``json_patch`` (structured edits).

Pure standard library (``json`` + ``os``); deterministic; imports no
``PySide6``.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class MatchReport:
    """Outcome of matching an actual payload against an expected one."""

    ok: bool
    mismatches: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict view for executor / MCP responses."""
        return {"ok": self.ok, "mismatches": list(self.mismatches)}


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    return left == right


def _diff_dict(actual: Dict, expected: Dict, path: str,
               diffs: List[Dict[str, Any]]) -> None:
    for key, value in expected.items():
        child = f"{path}.{key}"
        if key not in actual:
            diffs.append({"path": child, "kind": "missing", "expected": value})
        else:
            diffs.extend(diff_json(actual[key], value, path=child))
    for key, value in actual.items():
        if key not in expected:
            diffs.append({"path": f"{path}.{key}", "kind": "extra",
                          "actual": value})


def _diff_list(actual: List, expected: List, path: str,
               diffs: List[Dict[str, Any]]) -> None:
    common = min(len(actual), len(expected))
    for index in range(common):
        diffs.extend(diff_json(actual[index], expected[index],
                               path=f"{path}[{index}]"))
    for index in range(common, len(expected)):
        diffs.append({"path": f"{path}[{index}]", "kind": "missing",
                      "expected": expected[index]})
    for index in range(common, len(actual)):
        diffs.append({"path": f"{path}[{index}]", "kind": "extra",
                      "actual": actual[index]})


def diff_json(actual: Any, expected: Any, *,
              path: str = "$") -> List[Dict[str, Any]]:
    """Return path-tagged differences between ``actual`` and ``expected``."""
    diffs: List[Dict[str, Any]] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        _diff_dict(actual, expected, path, diffs)
    elif isinstance(expected, list) and isinstance(actual, list):
        _diff_list(actual, expected, path, diffs)
    elif not _json_equal(actual, expected):
        diffs.append({"path": path, "kind": "changed", "actual": actual,
                      "expected": expected})
    return diffs


def _type_match(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return True
    return type(left) is type(right)


def match_json(actual: Any, expected: Any, *, ignore: Iterable[str] = (),
               match_type: bool = False, partial: bool = False) -> MatchReport:
    """Match ``actual`` against ``expected`` with optional relaxed rules."""
    ignored = set(ignore)
    kept: List[Dict[str, Any]] = []
    for diff in diff_json(actual, expected):
        if diff["path"] in ignored:
            continue
        if partial and diff["kind"] == "extra":
            continue
        if (match_type and diff["kind"] == "changed"
                and _type_match(diff["actual"], diff["expected"])):
            continue
        kept.append(diff)
    return MatchReport(ok=not kept, mismatches=kept)


def _normalize(value: Any, drop: set) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(val, drop)
                for key, val in sorted(value.items()) if key not in drop}
    if isinstance(value, list):
        return [_normalize(item, drop) for item in value]
    return value


def normalize_json(value: Any, *, drop: Iterable[str] = ()) -> Any:
    """Return a canonical copy (sorted keys, ``drop`` keys removed anywhere)."""
    return _normalize(value, set(drop))


def snapshot_json(actual: Any, path: str) -> bool:
    """Golden-master: write ``actual`` if absent, else match the saved copy."""
    target = Path(os.path.realpath(path))
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(actual, indent=2, sort_keys=True),
                          encoding="utf-8")
        return True
    expected = json.loads(target.read_text(encoding="utf-8"))
    return match_json(actual, expected).ok
