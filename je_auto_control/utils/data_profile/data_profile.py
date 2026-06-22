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
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.stats.stats import describe

_NULLS = (None, "")
_TOP_N = 5


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _infer_type(non_null: Sequence[Any]) -> str:
    if not non_null:
        return "str"
    if all(_is_int(value) for value in non_null):
        return "int"
    if all(_is_number(value) for value in non_null):
        return "number"
    if all(isinstance(value, bool) for value in non_null):
        return "bool"
    return "str"


def _numeric_summary(kind: str, non_null: Sequence[Any]) -> Dict[str, Any]:
    if kind not in ("int", "number") or not non_null:
        return {}
    stats = describe([float(value) for value in non_null])
    return {"min": stats["min"], "max": stats["max"], "mean": stats["mean"]}


def _column_profile(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = [row.get(name) for row in rows]
    non_null = [value for value in values if value not in _NULLS]
    null_count = len(values) - len(non_null)
    kind = _infer_type(non_null)
    distinct = len({_hashable(value) for value in non_null})
    top = Counter(_hashable(value) for value in non_null).most_common(_TOP_N)
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
    return value if isinstance(value, (str, int, float, bool)) else repr(value)


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
    non-null value is distinct, and carries numeric ``min``/``max`` bounds.
    """
    profile = profile_rows(rows, columns)
    schema: Dict[str, Any] = {}
    for name, column in profile["columns"].items():
        rule: Dict[str, Any] = {"type": column["inferred_type"]}
        if column["null_count"] == 0 and column["count"] > 0:
            rule["required"] = True
        if column.get("unique"):
            rule["unique"] = True
        if "min" in column:
            rule["min"] = column["min"]
            rule["max"] = column["max"]
        schema[name] = rule
    return schema
