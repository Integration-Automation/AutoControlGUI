"""Round-3 regression: data_source SQLite URI must percent-encode the path.

The sibling bug in ``sql/sql_query.py`` was fixed by its own agent; this pins
the identical raw-f-string URI defect in ``data_source._load_sqlite`` — a path
containing ``%``/``#`` opened the wrong file (or none) despite the pre-check
passing.
"""
import sqlite3

import pytest

from je_auto_control.utils.data_source.data_source import load_rows


def _make_db(path):
    """Create a one-row SQLite DB at ``path`` (a normal, non-URI filename)."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (name TEXT)")
        conn.execute("INSERT INTO t (name) VALUES ('ok')")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("filename", ["weird%41name.db", "has#hash.db"])
def test_sqlite_source_opens_path_with_uri_special_chars(tmp_path, filename):
    """A DB whose filename contains ``%``/``#`` loads its rows correctly."""
    db_path = tmp_path / filename
    _make_db(db_path)
    rows = load_rows(
        {"kind": "sqlite", "path": str(db_path), "query": "SELECT name FROM t"})
    assert rows == [{"name": "ok"}]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
