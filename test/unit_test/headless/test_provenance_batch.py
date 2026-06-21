"""Headless tests for SLSA provenance. Pure stdlib, no Qt imports."""
import hashlib
import json

import je_auto_control as ac
from je_auto_control.utils.provenance import (
    build_provenance, subject_for, subject_for_bytes, verify_provenance,
    write_provenance)


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_subject_for_bytes_digest():
    subject = subject_for_bytes("inline", b"hello")
    assert subject["name"] == "inline"
    assert subject["digest"]["sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_subject_for_file(tmp_path):
    path = _write(tmp_path, "a.txt", b"hello")
    subject = subject_for(path)
    assert subject["name"] == "a.txt"
    assert subject["digest"]["sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_build_provenance_structure():
    stmt = build_provenance([subject_for_bytes("a", b"x")], builder_id="ci",
                            metadata={"invocation_id": "run-1"})
    assert stmt["_type"] == "https://in-toto.io/Statement/v1"
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v1"
    assert stmt["predicate"]["runDetails"]["builder"]["id"] == "ci"
    assert stmt["predicate"]["runDetails"]["metadata"]["invocationId"] == "run-1"


def test_verify_clean_and_tamper(tmp_path):
    path = _write(tmp_path, "a.txt", b"hello")
    stmt = build_provenance([subject_for(path)])
    assert verify_provenance(stmt, {"a.txt": path}) == []
    _write(tmp_path, "a.txt", b"TAMPERED")
    mismatches = verify_provenance(stmt, {"a.txt": path})
    assert len(mismatches) == 1 and mismatches[0]["name"] == "a.txt"


def test_write_provenance_round_trip(tmp_path):
    stmt = build_provenance([subject_for_bytes("a", b"x")])
    out = write_provenance(stmt, str(tmp_path / "prov.json"))
    with open(out, encoding="utf-8") as handle:
        assert json.load(handle)["predicateType"] == stmt["predicateType"]


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    path = _write(tmp_path, "art.bin", b"payload")
    rec = ac.execute_action([[
        "AC_build_provenance", {"paths": json.dumps([path])},
    ]])
    stmt = next(v for v in rec.values() if isinstance(v, dict))["statement"]
    rec2 = ac.execute_action([[
        "AC_verify_provenance",
        {"statement": json.dumps(stmt),
         "files": json.dumps({"art.bin": path})},
    ]])
    payload = next(v for v in rec2.values() if isinstance(v, dict))
    assert payload["ok"] is True


def test_wiring():
    assert {"AC_build_provenance", "AC_verify_provenance"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_build_provenance", "ac_verify_provenance"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_build_provenance", "AC_verify_provenance"} <= cmds


def test_facade_exports():
    for attr in ("build_provenance", "verify_provenance", "subject_for",
                 "subject_for_bytes", "write_provenance"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
