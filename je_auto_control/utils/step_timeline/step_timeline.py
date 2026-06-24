"""Build a per-run step waterfall and find the run's bottleneck steps.

The action profiler aggregates timings by step *name* across many runs — great for
"which action is slow on average", useless for "why was *this* run slow". A single
run is an ordered timeline: step A ran, then B, then C, and one of them dominated.
``step_timeline`` turns one run's steps into a waterfall (each step's offset from
the start, duration and share of the total) and ranks the bottleneck steps, so you
can read a single slow run instead of an average.

A step is any dict with a name (default ``"name"``) and a ``duration``; an optional
``start`` places it on an absolute timeline (overlapping / parallel steps), else
steps are laid out back-to-back. Pure standard library; no device, no ``PySide6``.
"""
from typing import Any, Dict, List, Sequence

Step = Dict[str, Any]


def _normalize(steps: Sequence[Step], name_key: str, start_key: str,
               duration_key: str) -> List[Dict[str, Any]]:
    """Resolve each step to ``{name, start, end, duration}`` (sequential if no start)."""
    resolved, cursor = [], 0.0
    for step in steps:
        duration = float(step.get(duration_key, 0.0) or 0.0)
        raw_start = step.get(start_key)
        start = float(raw_start) if raw_start is not None else cursor
        end = start + duration
        cursor = max(cursor, end)
        resolved.append({"name": str(step.get(name_key, "")), "start": start,
                         "end": end, "duration": duration})
    return resolved


def build_timeline(steps: Sequence[Step], *, name_key: str = "name",
                   start_key: str = "start",
                   duration_key: str = "duration") -> Dict[str, Any]:
    """Return a waterfall timeline for one run.

    ``{steps:[{name, offset, duration, pct}], total, busy, bottleneck,
    parallelism}`` — ``total`` is the wall-clock span, ``busy`` the summed step
    time, ``parallelism`` = busy / total (1.0 for a purely sequential run),
    ``bottleneck`` the longest single step.
    """
    resolved = _normalize(steps, name_key, start_key, duration_key)
    if not resolved:
        return {"steps": [], "total": 0.0, "busy": 0.0, "bottleneck": None,
                "parallelism": 0.0}
    base = min(step["start"] for step in resolved)
    span = max(step["end"] for step in resolved) - base
    busy = sum(step["duration"] for step in resolved)
    rows = [{"name": step["name"], "offset": round(step["start"] - base, 6),
             "duration": step["duration"],
             "pct": round(step["duration"] / span * 100, 1) if span > 0 else 0.0}
            for step in resolved]
    bottleneck = max(resolved, key=lambda step: step["duration"])
    return {"steps": rows, "total": round(span, 6), "busy": round(busy, 6),
            "bottleneck": {"name": bottleneck["name"],
                           "duration": bottleneck["duration"]},
            "parallelism": round(busy / span, 3) if span > 0 else 1.0}


def critical_steps(steps: Sequence[Step], *, name_key: str = "name",
                   start_key: str = "start", duration_key: str = "duration",
                   top: int = 3) -> List[Dict[str, Any]]:
    """Return the ``top`` steps that dominate the run, longest first.

    Each entry is ``{name, duration, pct}`` where ``pct`` is the step's share of
    the total step time — the bottlenecks worth optimising.
    """
    resolved = _normalize(steps, name_key, start_key, duration_key)
    busy = sum(step["duration"] for step in resolved) or 1.0
    ranked = sorted(resolved, key=lambda step: step["duration"], reverse=True)
    return [{"name": step["name"], "duration": step["duration"],
             "pct": round(step["duration"] / busy * 100, 1)}
            for step in ranked[:max(1, int(top))]]
