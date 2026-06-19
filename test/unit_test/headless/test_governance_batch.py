"""Headless tests for the maker-checker approval gate. State is in-memory
(no db_path) or a tmp JSON file; pure stdlib, no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.governance import ApprovalGate


def test_request_returns_pending_token():
    gate = ApprovalGate()
    token = gate.request("delete prod table", requester="alice")
    assert token and gate.status(token) == "pending"
    assert gate.is_approved(token) is False


def test_checker_must_differ_from_maker():
    gate = ApprovalGate()
    token = gate.request("wire funds", requester="alice")
    # self-approval is refused (segregation of duties)
    assert gate.approve(token, "alice") is False
    assert gate.is_approved(token) is False
    # a different checker succeeds
    assert gate.approve(token, "bob") is True
    assert gate.is_approved(token) is True
    assert gate.status(token) == "approved"


def test_reject_blocks_approval():
    gate = ApprovalGate()
    token = gate.request("deploy", requester="alice")
    assert gate.reject(token, "bob") is True
    assert gate.is_approved(token) is False
    # a decided request cannot be re-decided
    assert gate.approve(token, "carol") is False


def test_pending_lists_only_open_requests():
    gate = ApprovalGate()
    open_token = gate.request("a", requester="alice")
    closed = gate.request("b", requester="alice")
    gate.approve(closed, "bob")
    tokens = {r["token"] for r in gate.pending()}
    assert tokens == {open_token}


def test_persists_across_instances(tmp_path):
    db = str(tmp_path / "gate.json")
    token = ApprovalGate(db).request("ship", requester="alice")
    # a fresh instance (e.g. the checker's process) sees the request
    assert ApprovalGate(db).approve(token, "bob") is True
    assert ApprovalGate(db).is_approved(token) is True


def test_unknown_token_is_safe():
    gate = ApprovalGate()
    assert gate.status("nope") is None
    assert gate.is_approved("nope") is False
    assert gate.approve("nope", "bob") is False


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    db = str(tmp_path / "g.json")
    rec = ac.execute_action([
        ["AC_approval_request", {"action": "x", "requester": "alice",
                                 "db": db}],
    ])
    token = next(v for v in rec.values() if isinstance(v, dict))["token"]
    rec2 = ac.execute_action([
        ["AC_approval_approve", {"token": token, "approver": "bob",
                                 "db": db}],
        ["AC_approval_status", {"token": token, "db": db}],
    ])
    statuses = [v for v in rec2.values() if isinstance(v, dict)]
    assert any(v.get("approved") is True for v in statuses)


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_approval_request", "AC_approval_approve",
            "AC_approval_reject", "AC_approval_status"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_approval_request", "ac_approval_approve",
            "ac_approval_reject", "ac_approval_status"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_approval_request", "AC_approval_approve",
            "AC_approval_reject", "AC_approval_status"} <= cmds


def test_facade_export():
    assert hasattr(ac, "ApprovalGate")
    assert "ApprovalGate" in ac.__all__
