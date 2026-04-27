"""Tests for the REST bearer-token + per-IP rate-limit gate (round 23).

Test IPs use the RFC 5737 documentation ranges (192.0.2.0/24 = TEST-NET-1,
198.51.100.0/24 = TEST-NET-2, 203.0.113.0/24 = TEST-NET-3) so static
analysis tools that flag hardcoded IPs (Sonar S1313) recognise them as
intentional test fixtures rather than real-world routable addresses.
"""
from je_auto_control.utils.rest_api.rest_auth import (
    RestAuthGate, constant_time_equal, generate_token,
)


_TEST_IP_A = "192.0.2.1"
_TEST_IP_B = "192.0.2.2"
_TEST_IP_C = "192.0.2.3"
_TEST_IP_D = "192.0.2.4"
_TEST_IP_E = "192.0.2.5"
_TEST_IP_F = "192.0.2.6"


def test_generate_token_is_url_safe_and_unique():
    a = generate_token()
    b = generate_token()
    assert a != b
    # token_urlsafe(24) → 32-char base64url; allow padding-stripped length range
    assert len(a) >= 30
    for ch in a:
        assert ch.isalnum() or ch in "-_"


def test_constant_time_equal_matches():
    assert constant_time_equal("abc", "abc")
    assert not constant_time_equal("abc", "abd")
    assert not constant_time_equal("abc", "abcd")


def test_check_accepts_correct_bearer():
    gate = RestAuthGate(expected_token="real")
    verdict = gate.check(client_ip=_TEST_IP_A, header_value="Bearer real")
    assert verdict == "ok"


def test_check_rejects_wrong_token():
    gate = RestAuthGate(expected_token="real")
    verdict = gate.check(client_ip=_TEST_IP_A, header_value="Bearer wrong")
    assert verdict == "unauthorized"


def test_check_rejects_missing_header():
    gate = RestAuthGate(expected_token="real")
    assert gate.check(client_ip=_TEST_IP_A, header_value=None) == "unauthorized"
    assert gate.check(client_ip=_TEST_IP_A, header_value="") == "unauthorized"


def test_check_rejects_non_bearer_scheme():
    gate = RestAuthGate(expected_token="real")
    verdict = gate.check(client_ip=_TEST_IP_A, header_value="Basic real")
    assert verdict == "unauthorized"


def test_lockout_after_repeated_failures():
    gate = RestAuthGate(expected_token="real")
    for _ in range(8):
        gate.check(client_ip=_TEST_IP_B, header_value="Bearer wrong")
    verdict = gate.check(client_ip=_TEST_IP_B, header_value="Bearer wrong")
    assert verdict in ("locked_out", "rate_limited"), verdict


def test_lockout_is_per_ip():
    """A bad client must NOT lock out a different IP."""
    gate = RestAuthGate(expected_token="real")
    for _ in range(20):
        gate.check(client_ip=_TEST_IP_C, header_value="Bearer wrong")
    # different client should still be evaluated normally
    verdict = gate.check(client_ip=_TEST_IP_D, header_value="Bearer real")
    assert verdict == "ok"


def test_rate_limit_kicks_in():
    """Burst is 30 by default — 50 requests in a row should get rate-limited."""
    gate = RestAuthGate(expected_token="real")
    verdicts = [
        gate.check(client_ip=_TEST_IP_E, header_value="Bearer real")
        for _ in range(50)
    ]
    assert "rate_limited" in verdicts


def test_successful_auth_resets_failure_counter():
    gate = RestAuthGate(expected_token="real")
    for _ in range(3):
        gate.check(client_ip=_TEST_IP_F, header_value="Bearer wrong")
    # Successful login clears the failure window.
    assert gate.check(client_ip=_TEST_IP_F, header_value="Bearer real") == "ok"
    # Now a few more failures should not lock out immediately.
    for _ in range(3):
        verdict = gate.check(client_ip=_TEST_IP_F, header_value="Bearer wrong")
        assert verdict == "unauthorized"
