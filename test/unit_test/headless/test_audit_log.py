"""Tests for the tamper-evident audit log (round 25)."""
import sqlite3

import pytest

from je_auto_control.utils.remote_desktop.audit_log import AuditLog


@pytest.fixture()
def audit(tmp_path):
    log = AuditLog(path=tmp_path / "audit.db")
    yield log
    log.close()


def test_empty_chain_verifies_ok(audit):
    result = audit.verify_chain()
    assert result.ok is True
    assert result.broken_at_id is None
    assert result.total_rows == 0


def test_fresh_rows_verify_ok(audit):
    for i in range(5):
        audit.log("test", host_id=f"h{i}", detail=f"row {i}")
    result = audit.verify_chain()
    assert result.ok is True
    assert result.total_rows == 5


def test_tamper_detected_via_direct_sql(tmp_path):
    db_path = tmp_path / "audit.db"
    log = AuditLog(path=db_path)
    for i in range(5):
        log.log("test", host_id=f"h{i}", detail=f"row {i}")
    log.close()

    # Simulate an attacker editing one row directly.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE events SET detail = 'TAMPERED' WHERE id = 3")
        conn.commit()
    finally:
        conn.close()

    log2 = AuditLog(path=db_path)
    try:
        result = log2.verify_chain()
        assert result.ok is False
        assert result.broken_at_id == 3
        assert result.total_rows == 5
    finally:
        log2.close()


def test_legacy_table_without_hash_columns_is_backfilled(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE events ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL, event_type TEXT NOT NULL,"
            " host_id TEXT, viewer_id TEXT, detail TEXT)"
        )
        for i in range(3):
            conn.execute(
                "INSERT INTO events (ts, event_type, host_id, detail)"
                " VALUES (?, ?, ?, ?)",
                (f"2026-04-27T0{i}:00:00+00:00", "legacy",
                 f"h{i}", f"legacy {i}"),
            )
        conn.commit()
    finally:
        conn.close()

    log = AuditLog(path=db_path)
    try:
        result = log.verify_chain()
        assert result.ok is True
        assert result.total_rows == 3
    finally:
        log.close()


def test_clear_returns_deleted_count_and_resets_chain(audit):
    for _ in range(4):
        audit.log("test", host_id="h", detail="x")
    deleted = audit.clear()
    assert deleted == 4
    # Empty chain after clear.
    assert audit.verify_chain().total_rows == 0
    # Inserting again should still produce a valid chain.
    audit.log("test", host_id="h", detail="x")
    assert audit.verify_chain().ok is True


def test_query_filters_by_event_type(audit):
    audit.log("kindA", host_id="h1", detail="a")
    audit.log("kindB", host_id="h2", detail="b")
    audit.log("kindA", host_id="h3", detail="c")
    rows = audit.query(event_type="kindA")
    assert len(rows) == 2
    assert all(r["event_type"] == "kindA" for r in rows)


def test_query_filters_by_host_id(audit):
    audit.log("test", host_id="alpha", detail="a")
    audit.log("test", host_id="beta", detail="b")
    rows = audit.query(host_id="alpha")
    assert len(rows) == 1 and rows[0]["host_id"] == "alpha"


def test_query_returns_rows_in_descending_id_order(audit):
    for i in range(3):
        audit.log("test", host_id="h", detail=f"row {i}")
    rows = audit.query()
    assert [r["detail"] for r in rows] == ["row 2", "row 1", "row 0"]
