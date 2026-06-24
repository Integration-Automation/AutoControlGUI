"""Diff two run traces — what changed between two executions of a flow.

A run history tells you a run *failed*, but not *what changed* from the run that
passed: which step was added or dropped, which step flipped pass→fail, which step
got slower. ``run_diff`` aligns the two step sequences with a longest-common-
subsequence walk (so an inserted / removed step shifts the rest into place instead
of mis-pairing everything) and classifies the differences:

* **added** / **removed** steps (present in only one run),
* **status flips** (an aligned step whose status changed — with the new failure's
  :func:`failure_signature` when it carries an ``error``),
* **timing regressions** (an aligned step that got ``regress_factor`` x slower).

A step is any dict with a name key (default ``"name"``) and optional ``status`` /
``duration`` / ``error``. Pure standard library; no device, no ``PySide6``.
"""
from typing import Any, Dict, List, Sequence

Step = Dict[str, Any]


def _lcs_pairs(left: Sequence[str], right: Sequence[str]) -> List[tuple]:
    """Return aligned ``(i, j)`` index pairs of the longest common subsequence."""
    n, m = len(left), len(right)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if left[i] == right[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if left[i] == right[j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _status_flip(before: Step, after: Step, name: str) -> Dict[str, Any]:
    """Build a status-flip record, attaching a signature for a new error."""
    flip = {"name": name, "from": before.get("status"),
            "to": after.get("status")}
    error = after.get("error")
    if error:
        from je_auto_control.utils.failure_signature import failure_signature
        flip["signature"] = failure_signature(str(error))
    return flip


def _regression(before: Step, after: Step, name: str,
                factor: float) -> Dict[str, Any]:
    """Return a timing-regression record, or ``{}`` if not a regression."""
    prev, curr = before.get("duration"), after.get("duration")
    if not isinstance(prev, (int, float)) or not isinstance(curr, (int, float)):
        return {}
    if prev > 0 and curr >= prev * float(factor):
        return {"name": name, "before": float(prev), "after": float(curr),
                "ratio": round(curr / prev, 3)}
    return {}


def _aligned_changes(before: Sequence[Step], after: Sequence[Step],
                     names: Sequence[str], pairs: List[tuple],
                     factor: float) -> tuple:
    """Classify the LCS-aligned pairs into (status flips, timing regressions)."""
    flips, regressions = [], []
    for i, j in pairs:
        if before[i].get("status") != after[j].get("status"):
            flips.append(_status_flip(before[i], after[j], names[i]))
        regression = _regression(before[i], after[j], names[i], factor)
        if regression:
            regressions.append(regression)
    return flips, regressions


def _keys(steps: Sequence[Step], key: str) -> List[str]:
    return [str(step.get(key, "")) for step in steps]


def _unmatched(steps: Sequence[Step], matched: set) -> List[Step]:
    return [steps[k] for k in range(len(steps)) if k not in matched]


def diff_runs(before: Sequence[Step], after: Sequence[Step], *,
              key: str = "name", regress_factor: float = 1.5) -> Dict[str, Any]:
    """Diff two step sequences into ``{added, removed, status_flips,
    timing_regressions, aligned, identical}``.

    Steps are aligned by their ``key`` value via LCS; ``regress_factor`` is the
    slowdown ratio that counts as a timing regression.
    """
    left, right = _keys(before, key), _keys(after, key)
    pairs = _lcs_pairs(left, right)
    flips, regressions = _aligned_changes(before, after, left, pairs,
                                          regress_factor)
    added = _unmatched(after, {j for _, j in pairs})
    removed = _unmatched(before, {i for i, _ in pairs})
    return {"added": added, "removed": removed, "status_flips": flips,
            "timing_regressions": regressions, "aligned": len(pairs),
            "identical": not any((added, removed, flips, regressions))}


def summarize_run_diff(diff: Dict[str, Any]) -> str:
    """Render a one-line human summary of a :func:`diff_runs` result."""
    if diff.get("identical"):
        return "no change"
    parts = []
    for label, field in (("+{} added", "added"), ("-{} removed", "removed"),
                         ("{} status flip(s)", "status_flips"),
                         ("{} regression(s)", "timing_regressions")):
        count = len(diff.get(field, []))
        if count:
            parts.append(label.format(count))
    return ", ".join(parts)
