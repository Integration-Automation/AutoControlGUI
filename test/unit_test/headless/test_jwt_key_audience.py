"""JWT: an empty or non-string key, an unclaimed audience and non-JSON claims are JwtErrors (fake keys only).

An empty key signed and verified, so a secret from an unset environment
variable let anyone mint accepted tokens; a token carrying ``aud`` verified
wherever the key was shared (RFC 7519 4.1.3 says reject); ``None`` keys and
``datetime`` claims escaped as bare ``TypeError``.
"""
import base64
import datetime
import hashlib
import hmac
import json

import pytest

from je_auto_control.utils.jwt import ClaimsPolicy, JwtError, decode_jwt, encode_jwt

KEY = "test-" + "k" * 16


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _token_signed_with(key: bytes, claims: dict) -> str:
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(claims).encode())
    signature = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(signature)}"


@pytest.mark.parametrize("key", ["", b"", bytearray()])
def test_an_empty_key_neither_signs_nor_verifies(key):
    with pytest.raises(JwtError, match="empty"):
        encode_jwt({"sub": "a"}, key)
    with pytest.raises(JwtError, match="empty"):
        decode_jwt(_token_signed_with(b"", {"sub": "a"}), key)


@pytest.mark.parametrize("key", [None, 7, ["k"]])
def test_a_non_string_key_is_a_jwt_error(key):
    with pytest.raises(JwtError, match="key must be"):
        encode_jwt({"sub": "a"}, key)
    with pytest.raises(JwtError, match="key must be"):
        decode_jwt(encode_jwt({"sub": "a"}, KEY), key)


def test_bytes_keys_still_work():
    token = encode_jwt({"sub": "a"}, KEY.encode())
    assert decode_jwt(token, bytearray(KEY.encode())) == {"sub": "a"}


def test_a_token_with_an_audience_needs_the_policy_to_name_it():
    token = encode_jwt({"sub": "a", "aud": "svc-a"}, KEY)
    with pytest.raises(JwtError, match="aud"):
        decode_jwt(token, KEY)
    assert decode_jwt(token, KEY, ClaimsPolicy(audience="svc-a"))["aud"] == "svc-a"
    with pytest.raises(JwtError, match="mismatch"):
        decode_jwt(token, KEY, ClaimsPolicy(audience="svc-b"))


@pytest.mark.parametrize("aud", [["svc-a", "svc-b"], []])
def test_an_audience_list_is_enforced_too(aud):
    token = encode_jwt({"aud": aud}, KEY)
    with pytest.raises(JwtError):
        decode_jwt(token, KEY)


def test_a_token_without_an_audience_needs_none():
    assert decode_jwt(encode_jwt({"sub": "a"}, KEY), KEY) == {"sub": "a"}
    assert decode_jwt(encode_jwt({"aud": None}, KEY), KEY) == {"aud": None}


def test_the_adapter_reports_an_unclaimed_audience():
    from je_auto_control.utils.executor.action_executor import _jwt_decode
    token = encode_jwt({"aud": "svc-a"}, KEY)
    result = _jwt_decode(token, KEY)
    assert result["ok"] is False and "aud" in result["error"]
    assert _jwt_decode(token, KEY, audience="svc-a")["ok"] is True


@pytest.mark.parametrize("claims", [
    {"exp": datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)},
    {"n": float("nan")},
    {"n": float("inf")},
    {"s": {1, 2}},
])
def test_claims_that_are_not_json_are_a_jwt_error(claims):
    with pytest.raises(JwtError, match="JSON"):
        encode_jwt(claims, KEY)


def test_a_header_that_is_not_json_is_a_jwt_error():
    with pytest.raises(JwtError, match="JSON"):
        encode_jwt({"sub": "a"}, KEY, headers={"kid": object()})
