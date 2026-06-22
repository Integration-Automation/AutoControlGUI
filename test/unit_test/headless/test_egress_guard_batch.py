"""Headless tests for the network egress allowlist guard. No real network is
used — enforcement happens before any socket is opened. Pure stdlib, no Qt
imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.egress import (
    EgressBlocked, EgressPolicy, get_egress_policy, set_egress_policy)


@pytest.fixture(autouse=True)
def _reset_policy():
    """Keep the module-level policy at allow-all around every test."""
    set_egress_policy(None, None)
    yield
    set_egress_policy(None, None)


def test_allow_all_by_default():
    assert EgressPolicy().is_allowed("https://anything.test/path") is True


def test_allowlist_is_default_deny():
    policy = EgressPolicy(allow=["*.example.com"])
    assert policy.is_allowed("https://api.example.com/v1") is True
    assert policy.is_allowed("https://evil.test/") is False
    with pytest.raises(EgressBlocked):
        policy.check("https://evil.test/")


def test_deny_overrides_allow():
    policy = EgressPolicy(allow=["*.example.com"], deny=["bad.example.com"])
    assert policy.is_allowed("https://ok.example.com") is True
    assert policy.is_allowed("https://bad.example.com") is False


def test_deny_only_mode_allows_others():
    policy = EgressPolicy(deny=["tracker.test"])
    assert policy.is_allowed("https://tracker.test") is False
    assert policy.is_allowed("https://fine.test") is True


def test_empty_allowlist_blocks_everything():
    policy = EgressPolicy(allow=[])
    assert policy.is_allowed("https://anything.test") is False


def test_comma_string_is_accepted():
    policy = EgressPolicy(allow="a.test, b.test")
    assert policy.is_allowed("https://a.test") is True
    assert policy.is_allowed("https://c.test") is False


def test_http_client_enforces_policy():
    from je_auto_control.utils.http_client.http_client import http_request
    set_egress_policy(allow=["allowed.test"])
    # blocked before any connection is attempted (scheme is irrelevant here)
    with pytest.raises(EgressBlocked):
        http_request("https://blocked.test/")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    ac.execute_action([["AC_egress_allow", {"allow": ["only.test"]}]])
    rec = ac.execute_action([
        ["AC_egress_check", {"url": "https://only.test/x"}],
    ])
    assert any(v.get("allowed") is True for v in rec.values()
               if isinstance(v, dict))
    rec2 = ac.execute_action([
        ["AC_egress_check", {"url": "https://other.test/x"}],
    ])
    assert any(v.get("allowed") is False for v in rec2.values()
               if isinstance(v, dict))
    ac.execute_action([["AC_egress_reset", {}]])
    assert get_egress_policy().is_allowed("https://other.test") is True


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_egress_allow", "AC_egress_check",
            "AC_egress_reset"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_egress_allow", "ac_egress_check", "ac_egress_reset"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_egress_allow", "AC_egress_check", "AC_egress_reset"} <= cmds


def test_facade_exports():
    for attr in ("EgressPolicy", "EgressBlocked", "get_egress_policy",
                 "set_egress_policy"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
