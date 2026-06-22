"""Diff two tabular row-sets by primary key (CDC-style change report).

The framework diffs *screens/snapshots* (``screen_state.diff_snapshots``,
``diff_screenshots``) but had nothing to diff two **tabular** row-sets by key —
the standard "what changed between yesterday's and today's extract" report.
This keys both sides, then reports added / removed / changed / unchanged rows
and per-cell changes.

Pure standard library; imports no ``PySide6``. Every function is pure (rows in,
dict/list out) so it is fully deterministic in CI.
"""
from typing import Any, Dict, List, Sequence, Tuple, Union

Key = Union[str, Sequence[str]]


def _key_columns(key: Key) -> List[str]:
    return [key] if isinstance(key, str) else list(key)


def _key_of(row: Dict[str, Any], columns: Sequence[str]) -> Tuple[Any, ...]:
    return tuple(row.get(column) for column in columns)


def _key_view(key_tuple: Tuple[Any, ...]) -> Any:
    return key_tuple[0] if len(key_tuple) == 1 else list(key_tuple)


def _index(rows: Sequence[Dict[str, Any]],
           columns: Sequence[str]) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    return {_key_of(row, columns): dict(row) for row in rows}


def diff_rows(old_rows: Sequence[Dict[str, Any]],
              new_rows: Sequence[Dict[str, Any]],
              key: Key) -> Dict[str, List[Any]]:
    """Diff ``old_rows`` against ``new_rows`` keyed by ``key``.

    Returns ``{added, removed, changed, unchanged}`` where ``added`` /
    ``removed`` / ``unchanged`` are row lists and ``changed`` holds
    ``{key, old, new}`` entries. On duplicate keys, the last row wins.
    """
    columns = _key_columns(key)
    old_index = _index(old_rows, columns)
    new_index = _index(new_rows, columns)
    added = [row for key_tuple, row in new_index.items()
             if key_tuple not in old_index]
    removed = [row for key_tuple, row in old_index.items()
               if key_tuple not in new_index]
    changed: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    for key_tuple, new_row in new_index.items():
        old_row = old_index.get(key_tuple)
        if old_row is None:
            continue
        if old_row == new_row:
            unchanged.append(new_row)
        else:
            changed.append({"key": _key_view(key_tuple),
                            "old": old_row, "new": new_row})
    return {"added": added, "removed": removed,
            "changed": changed, "unchanged": unchanged}


def cell_changes(old_rows: Sequence[Dict[str, Any]],
                 new_rows: Sequence[Dict[str, Any]],
                 key: Key) -> List[Dict[str, Any]]:
    """Return per-cell changes ``{key, column, old, new}`` for changed rows."""
    changes: List[Dict[str, Any]] = []
    for entry in diff_rows(old_rows, new_rows, key)["changed"]:
        old_row, new_row = entry["old"], entry["new"]
        for column in sorted(set(old_row) | set(new_row), key=str):
            if old_row.get(column) != new_row.get(column):
                changes.append({"key": entry["key"], "column": column,
                                "old": old_row.get(column),
                                "new": new_row.get(column)})
    return changes


def summarize_diff(diff: Dict[str, List[Any]]) -> Dict[str, int]:
    """Count each bucket of a :func:`diff_rows` result."""
    return {part: len(diff.get(part, []))
            for part in ("added", "removed", "changed", "unchanged")}
