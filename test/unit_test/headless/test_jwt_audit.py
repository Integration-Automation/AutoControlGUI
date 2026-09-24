"""JWT codec defects from the 2026-09-24 audit (fake key only).

Characters outside the base64url alphabet were dropped, so many token strings
verified for one signature; malformed header/payload JSON, non-object JSON,
non-numeric ``exp`` and non-string ``aud`` escaped as non-``JwtError``
exceptions; ``exp: NaN`` never expired; and an ``alg`` in extra headers
relabelled the token.
"""
import base64
import json

import pytest

from je_auto_control.utils.jwt import ClaimsPolicy, JwtError, decode_jwt, encode_jwt

KEY = "test-secret-1"


def _segment(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _token_with(header, payload):
    import hashlib
    import hmac
    head = _segment(header if isinstance(header, bytes) else json.dumps(header).encode())
    body = _segment(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
    signature = hmac.new(KEY.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_segment(signature)}"


def test_characters_outside_the_alphabet_are_refused():
    token = encode_jwt({"sub": "a"}, KEY)
    assert decode_jwt(token, KEY) == {"sub": "a"}
    with pytest.raises(JwtError):
        decode_jwt(token + "!!", KEY)


@pytest.mark.parametrize("header, payload", [
    (b"{not json", {"sub": "a"}),
    ({"alg": "HS256"}, b"[1, 2]"),
    (b"[]", {"sub": "a"}),
    ({"alg": "HS256"}, {"exp": "soon"}),
    ({"alg": "HS256"}, {"aud": 5}),
])
def test_every_malformed_token_is_a_jwt_error(header, payload):
    with pytest.raises(JwtError):
        decode_jwt(_token_with(header, payload), KEY, ClaimsPolicy(audience="svc"))


def test_a_nan_expiry_is_refused():
    token = _token_with({"alg": "HS256"}, b'{"exp": NaN}')
    with pytest.raises(JwtError):
        decode_jwt(token, KEY)


def test_extra_headers_cannot_change_the_algorithm():
    token = encode_jwt({"sub": "a"}, KEY, headers={"alg": "none", "kid": "k1"})
    header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    assert header["alg"] == "HS256" and header["kid"] == "k1"
    assert decode_jwt(token, KEY) == {"sub": "a"}
