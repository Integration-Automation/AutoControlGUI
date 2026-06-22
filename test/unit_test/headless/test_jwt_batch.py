"""Headless tests for the JWT codec. Pure stdlib, no Qt imports."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.jwt import (
    ClaimsPolicy, ExpiredTokenError, InvalidSignatureError, JwtError,
    decode_jwt, encode_jwt)

# Build the test key at runtime so secret scanners don't flag a literal.
KEY = "test-" + "k" * 16
OTHER_KEY = "other-" + "k" * 16


def test_round_trip():
    token = encode_jwt({"sub": "u1", "role": "admin"}, KEY)
    assert token.count(".") == 2
    claims = decode_jwt(token, KEY, now=1000)
    assert claims["sub"] == "u1"
    assert claims["role"] == "admin"


def test_expired_token():
    token = encode_jwt({"sub": "u1", "exp": 1000}, KEY)
    with pytest.raises(ExpiredTokenError):
        decode_jwt(token, KEY, now=2000)
    # leeway lets a just-expired token through
    policy = ClaimsPolicy(leeway=10)
    assert decode_jwt(token, KEY, policy, now=1005)["sub"] == "u1"


def test_not_yet_valid():
    token = encode_jwt({"sub": "u1", "nbf": 1000}, KEY)
    with pytest.raises(JwtError):
        decode_jwt(token, KEY, now=500)
    assert decode_jwt(token, KEY, now=1500)["sub"] == "u1"


def test_bad_signature_rejected():
    token = encode_jwt({"sub": "u1"}, KEY)
    with pytest.raises(InvalidSignatureError):
        decode_jwt(token, OTHER_KEY, now=1000)


def test_alg_none_rejected():
    import base64

    def seg(data):
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    forged = f"{seg({'alg': 'none', 'typ': 'JWT'})}.{seg({'sub': 'admin'})}."
    with pytest.raises(JwtError):
        decode_jwt(forged, KEY, now=1000)


def test_algorithm_allowlist_blocks_other_alg():
    token = encode_jwt({"sub": "u1"}, KEY, alg="HS512")
    with pytest.raises(JwtError):
        decode_jwt(token, KEY, ClaimsPolicy(algorithms=("HS256",)), now=1000)
    policy = ClaimsPolicy(algorithms=("HS512",))
    assert decode_jwt(token, KEY, policy, now=1000)["sub"] == "u1"


def test_audience_and_issuer():
    token = encode_jwt({"sub": "u1", "aud": "api", "iss": "me"}, KEY)
    policy = ClaimsPolicy(audience="api", issuer="me")
    assert decode_jwt(token, KEY, policy, now=1000)["sub"] == "u1"
    with pytest.raises(JwtError):
        decode_jwt(token, KEY, ClaimsPolicy(audience="other"), now=1000)
    with pytest.raises(JwtError):
        decode_jwt(token, KEY, ClaimsPolicy(issuer="someone-else"), now=1000)


def test_audience_list_membership():
    token = encode_jwt({"sub": "u1", "aud": ["api", "web"]}, KEY)
    assert decode_jwt(token, KEY, ClaimsPolicy(audience="web"), now=1000)["sub"] == "u1"


def test_malformed_token():
    with pytest.raises(JwtError):
        decode_jwt("not-a-jwt", KEY, now=1000)


def test_unsupported_algorithm_on_encode():
    with pytest.raises(JwtError):
        encode_jwt({"sub": "u1"}, KEY, alg="RS256")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    enc = ac.execute_action([[
        "AC_jwt_encode", {"claims": json.dumps({"sub": "u1"}), "key": KEY},
    ]])
    token = next(v for v in enc.values() if isinstance(v, dict))["token"]
    dec = ac.execute_action([["AC_jwt_decode", {"token": token, "key": KEY}]])
    payload = next(v for v in dec.values() if isinstance(v, dict))
    assert payload["ok"] is True
    assert payload["claims"]["sub"] == "u1"


def test_executor_reports_invalid():
    enc = ac.execute_action([[
        "AC_jwt_encode", {"claims": json.dumps({"sub": "u1"}), "key": KEY},
    ]])
    token = next(v for v in enc.values() if isinstance(v, dict))["token"]
    dec = ac.execute_action([[
        "AC_jwt_decode", {"token": token, "key": OTHER_KEY}]])
    payload = next(v for v in dec.values() if isinstance(v, dict))
    assert payload["ok"] is False
    assert "error" in payload


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_jwt_encode", "AC_jwt_decode"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_jwt_encode", "ac_jwt_decode"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_jwt_encode", "AC_jwt_decode"} <= cmds


def test_facade_exports():
    for attr in ("encode_jwt", "decode_jwt", "ClaimsPolicy", "JwtError",
                 "ExpiredTokenError", "InvalidSignatureError"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
