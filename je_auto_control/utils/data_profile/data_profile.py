"""Profile a row-set and infer a validation schema from observed data.

``data_quality.validate_rows`` *consumes* a hand-written schema and
``stats.describe`` summarises one numeric list — nothing surveys a whole
row-set to report per-column null fraction, cardinality, inferred type, value
ranges, and top values, nor proposes a starting schema. This is the
profiler step that feeds the existing validator.

Pure standard library (``collections`` + reuse of ``stats``); imports no
``PySide6``. All functions are pure (rows in, dict out) so they are fully
deterministic in CI.
"""
from collections import Counter
import math
from typing import Any, Dict, List, Optional, Sequence

_NULLS = (None, "")
_TOP_N = 5


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _infer_type(non_null: Sequence[Any]) -> str:
    """``int`` / ``number`` / ``bool`` / ``str``, or ``mixed`` when no one type holds.

    A mixed column (``30``, ``"unknown"``, ``41``) read as ``str``, so the
    inferred schema rejected the very rows it was inferred from.
    """
    if not non_null or all(isinstance(value, str) for value in non_null):
        return "str"
    if all(_is_int(value) for value in non_null):
        return "int"
    if all(_is_number(value) for value in non_null):
        return "number"
    if all(isinstance(value, bool) for value in non_null):
        return "bool"
    return "mixed"


def _as_float(value: Any) -> float:
    """``float(value)``, with an int past the float range as a signed infinity."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _numeric_summary(kind: str, non_null: Sequence[Any]) -> Dict[str, Any]:
    """``min`` / ``max`` / ``mean`` over the finite values, plus how many were not.

    One ``inf`` or ``nan`` used to abort the whole profile with ``ValueError``
    from ``statistics.pstdev``, which this summary never even reported.
    """
    if kind not in ("int", "number") or not non_null:
        return {}
    if kind == "int":
        return _int_summary(non_null)
    finite = [value for value in map(_as_float, non_null) if math.isfinite(value)]
    summary: Dict[str, Any] = {"min": None, "max": None, "mean": None,
                               "non_finite": len(non_null) - len(finite)}
    if finite:
        # Each term divided first: fsum of two 1e308 overflowed and aborted the profile.
        mean = math.fsum(value / len(finite) for value in finite)
        summary.update(min=min(finite), max=max(finite), mean=mean)
    return summary


def _int_summary(values: Sequence[int]) -> Dict[str, Any]:
    """Exact ``min`` / ``max`` of an int column; ``mean`` is ``None`` past the float range.

    Through ``float`` the bounds rounded past 2**53 and overflowed past 1e308,
    so the inferred schema rejected the column's own largest values.
    """
    try:
        mean: Optional[float] = sum(values) / len(values)
    except OverflowError:
        mean = None
    return {"min": min(values), "max": max(values), "mean": mean, "non_finite": 0}


def _column_profile(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = [row.get(name) for row in rows]
    non_null = [value for value in values if value not in _NULLS]
    null_count = len(values) - len(non_null)
    kind = _infer_type(non_null)
    counts = Counter(_hashable(value) for value in non_null)
    distinct = len(counts)
    top = [(key[1] if isinstance(key, tuple) else key, count)
           for key, count in counts.most_common(_TOP_N)]
    profile = {
        "count": len(values), "null_count": null_count,
        "null_fraction": (null_count / len(values)) if values else 0.0,
        "distinct": distinct,
        "unique": bool(non_null) and distinct == len(non_null),
        "inferred_type": kind,
        "top_values": [{"value": value, "count": count}
                       for value, count in top],
    }
    profile.update(_numeric_summary(kind, non_null))
    return profile


def _hashable(value: Any) -> Any:
    """A counting key; ``True`` is kept apart from ``1``, which it equals and hashes as."""
    if isinstance(value, bool):
        return ("bool", value)
    return value if isinstance(value, (str, int, float)) else repr(value)


def _column_names(rows: List[Dict[str, Any]],
                  columns: Optional[Sequence[str]]) -> List[str]:
    if columns is not None:
        return list(columns)
    seen: Dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(key, None)
    return list(seen)


def profile_rows(rows: List[Dict[str, Any]],
                 columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Profile ``rows`` into per-column statistics.

    Returns ``{row_count, columns: {name: {count, null_count, null_fraction,
    distinct, unique, inferred_type, top_values, [min, max, mean]}}}``.
    """
    names = _column_names(rows, columns)
    return {"row_count": len(rows),
            "columns": {name: _column_profile(name, rows) for name in names}}


def infer_schema(rows: List[Dict[str, Any]],
                 columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Infer a ``validate_rows``-compatible schema from observed ``rows``.

    A column is ``required`` when it has no nulls, ``unique`` when every
    non-null value is distinct, and carries numeric ``min``/``max`` bounds
    over its finite values (so an ``inf`` or ``NaN`` fails them). A ``mixed``
    column has no ``type`` rule.
    """
    profile = profile_rows(rows, columns)
    schema: Dict[str, Any] = {}
    for name, column in profile["columns"].items():
        rule: Dict[str, Any] = {}
        if column["inferred_type"] != "mixed":
            rule["type"] = column["inferred_type"]
        if column["null_count"] == 0 and column["count"] > 0:
            rule["required"] = True
        if column.get("unique"):
            rule["unique"] = True
        # A column with no finite value has bounds of None, which crashed validate_rows.
        if column.get("min") is not None:
            rule["min"] = column["min"]
            rule["max"] = column["max"]
        schema[name] = rule
    return schema
