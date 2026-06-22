"""Run ad-hoc read-only SQL queries for ``AC_sql_to_var`` / ``AC_assert_db``.

Generalises the SQLite reading already used by the data-source loader into
a standalone query helper that returns rows, a single row, or a scalar.
Queries are restricted to a single read-only ``SELECT``/``WITH`` statement
and run against a read-only connection; values are always bound as
parameters (never string-interpolated) to avoid SQL injection. Imports no
``PySide6`` so it stays fully headless.
"""
import sqlite3
from typing import Any, Dict, List, Optional, Union

from je_auto_control.utils.data_source.data_source import (
    _resolve_path, _validate_select,
)

_FetchResult = Union[List[Dict[str, Any]], Dict[str, Any], Any, None]


def _shape(cursor: sqlite3.Cursor, fetch: str) -> _FetchResult:
    """Reduce a cursor to the requested result shape."""
    if fetch in ("all", "rows"):
        return [dict(row) for row in cursor.fetchall()]
    if fetch == "one":
        row = cursor.fetchone()
        return dict(row) if row is not None else None
    if fetch == "scalar":
        row = cursor.fetchone()
        return row[0] if row is not None else None
    raise ValueError(
        f"unknown fetch mode {fetch!r}; expected all/one/scalar")


def query_sqlite(database: str, query: str,
                 params: Optional[Union[list, tuple, dict]] = None,
                 fetch: str = "all") -> _FetchResult:
    """Run a read-only SELECT/WITH against ``database`` and return its result.

    :param database: path to a SQLite database file (opened read-only).
    :param query: a single SELECT/WITH statement; reject anything else.
    :param params: values bound to ``?``/``:name`` placeholders in ``query``.
    :param fetch: ``all`` (list of row dicts), ``one`` (a row dict or None),
        or ``scalar`` (the first column of the first row, or None).
    """
    path = _resolve_path(database)
    statement = _validate_select(str(query))
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            statement, params if params is not None else ())
        return _shape(cursor, fetch)
