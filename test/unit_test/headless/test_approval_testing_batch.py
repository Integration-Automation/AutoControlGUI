"""Headless tests for approval testing (golden-master baselines). All files go
under a tmp dir; pure stdlib, no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.approval import (
    approve_artifact, pending_artifacts, verify_artifact)


def test_first_run_is_new_and_writes_received(tmp_path):
    d = str(tmp_path)
    result = verify_artifact("greeting", "hello", approvals_dir=d)
    assert result.status == "new"
    assert result.match is False
    assert pending_artifacts(d) == ["greeting"]


def test_approve_then_match(tmp_path):
    d = str(tmp_path)
    verify_artifact("greeting", "hello", approvals_dir=d)   # writes received
    approve_artifact("greeting", approvals_dir=d)           # promote baseline
    assert pending_artifacts(d) == []                        # received cleared
    result = verify_artifact("greeting", "hello", approvals_dir=d)
    assert result.status == "verified" and result.match is True


def test_mismatch_after_baseline(tmp_path):
    d = str(tmp_path)
    verify_artifact("greeting", "hello", approvals_dir=d)
    approve_artifact("greeting", approvals_dir=d)
    result = verify_artifact("greeting", "HELLO", approvals_dir=d)
    assert result.status == "mismatch" and result.match is False
    assert pending_artifacts(d) == ["greeting"]             # received re-written


def test_verified_clears_stale_received(tmp_path):
    d = str(tmp_path)
    verify_artifact("g", "v1", approvals_dir=d)
    approve_artifact("g", approvals_dir=d)
    verify_artifact("g", "DIFF", approvals_dir=d)           # leaves a received
    assert pending_artifacts(d) == ["g"]
    verify_artifact("g", "v1", approvals_dir=d)             # matches again
    assert pending_artifacts(d) == []                        # received removed


def test_bytes_content_supported(tmp_path):
    d = str(tmp_path)
    blob = b"\x89PNG\r\n"
    verify_artifact("img", blob, approvals_dir=d, extension="png")
    approve_artifact("img", approvals_dir=d, extension="png")
    assert verify_artifact("img", blob, approvals_dir=d,
                           extension="png").match is True


def test_approve_without_received_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        approve_artifact("nope", approvals_dir=str(tmp_path))


def test_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        verify_artifact("../escape", "x", approvals_dir=str(tmp_path))


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    d = str(tmp_path)
    rec = ac.execute_action([
        ["AC_verify_artifact", {"name": "a", "content": "x",
                                "approvals_dir": d}],
    ])
    assert any(v.get("status") == "new" for v in rec.values()
               if isinstance(v, dict))
    ac.execute_action([["AC_approve_artifact", {"name": "a",
                                                "approvals_dir": d}]])
    rec2 = ac.execute_action([
        ["AC_verify_artifact", {"name": "a", "content": "x",
                                "approvals_dir": d}],
    ])
    assert any(v.get("match") is True for v in rec2.values()
               if isinstance(v, dict))


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_verify_artifact", "AC_approve_artifact",
            "AC_pending_artifacts"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_verify_artifact", "ac_approve_artifact",
            "ac_pending_artifacts"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_verify_artifact", "AC_approve_artifact",
            "AC_pending_artifacts"} <= cmds


def test_facade_exports():
    for attr in ("verify_artifact", "approve_artifact", "pending_artifacts",
                 "ApprovalResult"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
