"""Protocol helpers follow their specs at the edges (pure, no network).

JWT headers with a list ``alg`` or a ``crit`` list (RFC 7515 4.1.11), an SSE
CRLF split so the ``\\n`` is a whole chunk (WHATWG 9.2.6), an escaped quote in
a Link parameter (RFC 8288 / RFC 9110 5.6.4), a newer ``traceparent`` version
(W3C Trace Context 4.3), mistyped problem members (RFC 9457 3.1), escaped
unreserved URL characters (RFC 3986 6.2.2.2) and empty cookie values
(RFC 6265 5.2).
"""
import base64
import hashlib
import hmac
import json

import pytest

from je_auto_control.utils.cookie_jar.cookie_jar import CookieJar
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.http_conditional.http_conditional import parse_cache_control
from je_auto_control.utils.http_problem.http_problem import parse_problem
from je_auto_control.utils.jwt.jwt_codec import JwtError, decode_jwt
from je_auto_control.utils.link_header.link_header import next_url, parse_link_header
from je_auto_control.utils.sse_client.sse_client import SSEParser
from je_auto_control.utils.trace_context.trace_context import parse_traceparent
from je_auto_control.utils.url_canon.url_canon import urls_equal

_KEY = b"k" * 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(header: dict, claims: dict) -> str:
    signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    signature = hmac.new(_KEY, signing.encode("ascii"), hashlib.sha256).digest()
    return f"{signing}.{_b64(signature)}"


def test_a_list_alg_is_a_jwt_error_not_a_type_error():
    with pytest.raises(JwtError):
        decode_jwt(_token({"alg": ["HS256"]}, {"sub": "a"}), _KEY)
    assert issubclass(JwtError, AutoControlException)


def test_a_critical_extension_is_rejected():
    with pytest.raises(JwtError, match="critical"):
        decode_jwt(_token({"alg": "HS256", "crit": ["exp-ext"], "exp-ext": 1}, {"sub": "a"}), _KEY)
    assert decode_jwt(_token({"alg": "HS256"}, {"sub": "a"}), _KEY)["sub"] == "a"


def test_a_crlf_split_before_a_lone_newline_still_dispatches():
    parser = SSEParser()
    events = [event for chunk in ["data: a\r", "\n", "\n"] for event in parser.feed(chunk)]
    assert [event.data for event in events] == ["a"]


def test_an_escaped_quote_in_a_link_parameter():
    header = '<https://x/2>; title="a\\"b; c"; rel="next"'
    assert next_url(header) == "https://x/2"
    assert parse_link_header(header)[0].params["title"] == 'a"b; c'


def test_an_escaped_quote_in_cache_control():
    assert parse_cache_control({"Cache-Control": 'private="a\\", b", max-age=5'})["max-age"] == 5


def test_a_newer_traceparent_version_continues_the_trace():
    context = parse_traceparent(
        "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01-future")
    assert context.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert context.trace_flags == 1


def test_mistyped_problem_members_are_ignored():
    problem = parse_problem({
        "headers": {"Content-Type": "application/problem+json"},
        "json": {"title": 42, "status": "404", "detail": ["x"], "instance": 7}})
    assert (problem.title, problem.status, problem.detail, problem.instance) == (None,) * 4
    good = parse_problem({"headers": {"Content-Type": "application/problem+json"},
                          "json": {"title": "Nope", "status": 404, "detail": "d"}})
    assert (good.title, good.status, good.detail) == ("Nope", 404, "d")
    flag = parse_problem({"headers": {"Content-Type": "application/problem+json"},
                          "json": {"status": True}})
    assert flag.status is None


def test_escaped_unreserved_characters_compare_equal():
    assert urls_equal("http://a/~b", "http://a/%7Eb")
    assert urls_equal("http://a/%2fb", "http://a/%2Fb")
    assert not urls_equal("http://a/%2Fb", "http://a//b")


def test_an_empty_cookie_value_is_kept():
    jar = CookieJar().update("flag=; Path=/")
    assert jar.cookie_header() == "flag="
    jar.update("flag=; Max-Age=0")
    assert jar.cookie_header() == ""
