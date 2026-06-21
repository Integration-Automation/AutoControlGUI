"""Cross-dataset referential-integrity checks (dbt-style generic tests).

``data_quality.validate_rows`` is strictly intra-row, single-table — its
``unique`` rule only dedupes within one batch. There was no parent/child
foreign-key check across two loaded tables, no composite-key uniqueness, and no
standalone accepted-values / row-count assertion. This adds those checks over
rows already loaded by ``data_source.load_rows`` / ``sql.query_sqlite``.

Pure standard library (``collections``); imports no ``PySide6``. Every function
is pure (rows in, report out), so it is fully deterministic in CI.
"""
from collections import Counter
from typing import Any, Dict, List, Sequence, Tuple, Union

Columns = Union[str, Sequence[str]]
_NULLS = (None, "")


def _columns(cols: Columns) -> List[str]:
    return [cols] if isinstance(cols, str) else list(cols)


def _key_view(key_tuple: Tuple[Any, ...]) -> Any:
    return key_tuple[0] if len(key_tuple) == 1 else list(key_tuple)


def check_foreign_key(child_rows: Sequence[Dict[str, Any]], child_col: str,
                      parent_rows: Sequence[Dict[str, Any]],
                      parent_col: str) -> Dict[str, Any]:
    """Every non-null ``child_col`` value must exist in ``parent_col`` (dbt rel)."""
    parent_values = {row.get(parent_col) for row in parent_rows}
    missing = [row.get(child_col) for row in child_rows
               if row.get(child_col) not in _NULLS
               and row.get(child_col) not in parent_values]
    return {"ok": not missing, "violations": len(missing),
            "missing": sorted(set(missing), key=str)}


def check_unique_key(rows: Sequence[Dict[str, Any]],
                     cols: Columns) -> Dict[str, Any]:
    """A single or composite key must be unique across ``rows``."""
    columns = _columns(cols)
    counts = Counter(tuple(row.get(col) for col in columns) for row in rows)
    duplicates = [{"key": _key_view(key_tuple), "count": count}
                  for key_tuple, count in counts.items() if count > 1]
    return {"ok": not duplicates, "duplicates": duplicates}


def check_accepted_values(rows: Sequence[Dict[str, Any]], col: str,
                          allowed: Sequence[Any]) -> Dict[str, Any]:
    """Every non-null ``col`` value must be within ``allowed``."""
    allowed_set = set(allowed)
    unexpected = [row.get(col) for row in rows
                  if row.get(col) not in _NULLS
                  and row.get(col) not in allowed_set]
    return {"ok": not unexpected, "violations": len(unexpected),
            "unexpected": sorted(set(unexpected), key=str)}


def check_row_count(rows: Sequence[Dict[str, Any]], minimum: Any = None,
                    maximum: Any = None) -> Dict[str, Any]:
    """The row count must fall within ``[minimum, maximum]`` when given."""
    count = len(rows)
    below = minimum is not None and count < minimum
    above = maximum is not None and count > maximum
    return {"ok": not (below or above), "count": count}
