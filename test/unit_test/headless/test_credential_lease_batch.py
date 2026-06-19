"""Headless tests for just-in-time credential leases. Clock and resolver are
injected, so expiry is deterministic without real time or a real vault. Pure
stdlib, no Qt imports."""
import time

import pytest

import je_auto_control as ac
from je_auto_control.utils.governance import (
    CredentialBroker, CredentialBrokerError)


class _Clock:
    """A manually advanced monotonic clock for deterministic expiry tests."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _broker(clock=time.monotonic):
    return CredentialBroker(resolver={"db_pw": "s3cr3t"}.get, clock=clock)


def test_redeem_while_valid_returns_value():
    broker = _broker()
    token = broker.lease("db_pw", ttl=60.0)
    assert broker.is_valid(token) is True
    assert broker.redeem(token) == "s3cr3t"


def test_redeem_after_expiry_raises():
    clock = _Clock()
    broker = _broker(clock=clock)
    token = broker.lease("db_pw", ttl=30.0)
    clock.now += 31.0                       # lease has expired
    assert broker.is_valid(token) is False
    with pytest.raises(CredentialBrokerError):
        broker.redeem(token)


def test_revoke_invalidates_lease():
    broker = _broker()
    token = broker.lease("db_pw", ttl=60.0)
    assert broker.revoke(token) is True
    assert broker.is_valid(token) is False
    assert broker.revoke(token) is False     # already gone


def test_redeem_without_resolver_raises():
    broker = CredentialBroker()              # no resolver configured
    token = broker.lease("db_pw", ttl=60.0)
    with pytest.raises(CredentialBrokerError):
        broker.redeem(token)


def test_unknown_secret_raises():
    broker = _broker()
    token = broker.lease("missing", ttl=60.0)
    with pytest.raises(CredentialBrokerError):
        broker.redeem(token)


def test_active_excludes_expired_and_hides_values():
    clock = _Clock()
    broker = _broker(clock=clock)
    live = broker.lease("db_pw", ttl=100.0)
    broker.lease("db_pw", ttl=10.0)          # will expire
    clock.now += 20.0
    active = broker.active()
    assert [a["token"] for a in active] == [live]
    assert "value" not in active[0] and "s3cr3t" not in str(active[0])


# --- wiring ---------------------------------------------------------------

def _valid(token):
    rec = ac.execute_action([["AC_lease_valid", {"token": token}]])
    return next(v for v in rec.values() if isinstance(v, dict))["valid"]


def test_executor_lifecycle_round_trip():
    rec = ac.execute_action([["AC_lease_secret", {"name": "x", "ttl": 60}]])
    token = next(v for v in rec.values() if isinstance(v, dict))["token"]
    assert _valid(token) is True            # leased: valid (default_broker)
    ac.execute_action([["AC_revoke_lease", {"token": token}]])
    assert _valid(token) is False           # revoked: no longer valid


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_lease_secret", "AC_lease_valid", "AC_revoke_lease",
            "AC_lease_active"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_lease_secret", "ac_lease_valid", "ac_revoke_lease",
            "ac_lease_active"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_lease_secret", "AC_lease_valid", "AC_revoke_lease",
            "AC_lease_active"} <= cmds


def test_facade_exports():
    for attr in ("CredentialBroker", "CredentialBrokerError",
                 "default_broker", "set_secret_resolver"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
