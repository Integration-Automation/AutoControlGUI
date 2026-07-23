"""Round-3 audit regressions: JSON persistence + SQL URI fixes.

Covers findings 3 (atomic JSON writes), 4 (cyclic ``$ref`` detection), and
11 (SQLite URI with special characters in the path). Headless: pure temp
files and an in-process SQLite DB, no real input.
"""
import os
import sqlite3

import pytest


# --- Finding 3: atomic writes --------------------------------------------

def _raise_oserror(_src, _dst):
    raise OSError("simulated crash mid-replace")


def test_write_action_json_is_atomic_on_crash(tmp_path, monkeypatch):
    from je_auto_control.utils.json.json_file import (
        read_action_json, write_action_json,
    )
    from je_auto_control.utils.exception.exceptions import (
        AutoControlJsonActionException,
    )
    target = tmp_path / "actions.json"
    write_action_json(str(target), [["old"]])
    assert read_action_json(str(target)) == [["old"]]

    monkeypatch.setattr(os, "replace", _raise_oserror)
    with pytest.raises(AutoControlJsonActionException):
        write_action_json(str(target), [["new"]])
    monkeypatch.undo()

    # Old content survives the interrupted write; no temp leftovers remain.
    assert read_action_json(str(target)) == [["old"]]
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "actions.json"]
    assert leftovers == []


def test_write_json_dict_is_atomic_on_crash(tmp_path, monkeypatch):
    from je_auto_control.utils.json_store.json_store import (
        read_json_dict, write_json_dict,
    )
    target = tmp_path / "state.json"
    write_json_dict(target, {"v": 1})
    assert read_json_dict(target) == {"v": 1}

    monkeypatch.setattr(os, "replace", _raise_oserror)
    with pytest.raises(OSError):
        write_json_dict(target, {"v": 2})
    monkeypatch.undo()

    assert read_json_dict(target) == {"v": 1}
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []


# --- Finding 4: cyclic $ref ------------------------------------------------

def test_validate_json_cyclic_ref_reports_clean_error():
    from je_auto_control.utils.json_schema.json_schema import validate_json
    result = validate_json(1, {"$ref": "#"})
    assert result.ok is False
    assert any(err["keyword"] == "$ref" for err in result.errors)


def test_validate_json_indirect_ref_cycle():
    from je_auto_control.utils.json_schema.json_schema import validate_json
    schema = {
        "$defs": {
            "a": {"$ref": "#/$defs/b"},
            "b": {"$ref": "#/$defs/a"},
        },
        "$ref": "#/$defs/a",
    }
    result = validate_json(1, schema)
    assert result.ok is False
    assert any(err["keyword"] == "$ref" for err in result.errors)


# --- Finding 11: SQLite URI with special path characters -----------------

def test_query_sqlite_special_char_path(tmp_path):
    from je_auto_control.utils.sql.sql_query import query_sqlite
    # '%41' would percent-decode to 'A' in a raw file: URI and '#' is unsafe too.
    db_path = tmp_path / "weird%41name#.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE t (id INTEGER, name TEXT)")
        connection.execute("INSERT INTO t VALUES (1, 'alice')")
        connection.commit()
    finally:
        connection.close()

    rows = query_sqlite(str(db_path), "SELECT name FROM t WHERE id = ?",
                        params=[1])
    assert rows == [{"name": "alice"}]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
