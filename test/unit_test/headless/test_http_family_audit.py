"""HTTP-family defects from the 2026-09-24 audit (no network).

The egress deny list matched the literal hostname while urllib connects to the
decoded one; responses and decompression were unbounded; repeated headers
collapsed to the last; an https-to-http redirect kept the credentials;
multipart names could inject parts and parsing ate line breaks and quoted
semicolons; Link parsing lost links after a quoted "<", took the last rel and
never resolved relative next links; URL normalisation broke IPv6 hosts,
dropped a password, merged "//" and rewrote queries; an invalid Max-Age kept a
deleted cookie; Unicode digits crashed the SSE parser.
"""
import gzip
import zlib
from email.message import Message

import pytest

from je_auto_control.utils.cookie_jar.cookie_jar import CookieJar
from je_auto_control.utils.egress.egress_policy import EgressPolicy
from je_auto_control.utils.http_client import http_client
from je_auto_control.utils.http_conditional.http_conditional import is_fresh
from je_auto_control.utils.http_content.http_content import build_accept, decode_body
from je_auto_control.utils.http_problem.http_problem import parse_problem
from je_auto_control.utils.link_header.link_header import next_url, paginate
from je_auto_control.utils.multipart.multipart import build_multipart, parse_multipart
from je_auto_control.utils.sse_client.sse_client import SSEParser
from je_auto_control.utils.url_canon.url_canon import normalize_url, urls_equal


@pytest.mark.parametrize("url", [
    "http://%65vil.com/", "http://EVIL.com./", "http://localhost./",
    "http://2130706433/", "http://0x7f.1/", "http://[::ffff:127.0.0.1]/",
])
def test_egress_deny_list_sees_the_host_urllib_connects_to(url):
    policy = EgressPolicy(deny=["evil.com", "127.0.0.1", "localhost"])
    assert policy.is_allowed(url) is False


def test_egress_allow_list_still_admits_ordinary_hosts():
    policy = EgressPolicy(allow=["*.example.com", "10.0.0.1"])
    assert policy.is_allowed("https://api.example.com/x")
    assert policy.is_allowed("http://10.0.0.1/")
    assert policy.is_allowed("http://167772161/")  # 10.0.0.1 spelled as one number
    assert not policy.is_allowed("https://cafe.be/")


class _Response:
    def __init__(self, body, headers):
        self._body = body
        self.status = 200
        self.headers = headers
        self.url = "https://x/"

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]


def test_a_response_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(OSError, match="exceeds"):
        http_client._read_response(_Response(b"x" * 11, Message()))


def test_repeated_headers_are_kept():
    headers = Message()
    headers["Set-Cookie"] = "a=1; Expires=Thu, 01 Jan 2099 00:00:00 GMT"
    headers["Set-Cookie"] = "b=2"
    headers["Link"] = '<https://x/p2>; rel="next"'
    headers["Link"] = '<https://x/p0>; rel="prev"'
    response = http_client._read_response(_Response(b"", headers))
    assert response["set_cookie"] == ["a=1; Expires=Thu, 01 Jan 2099 00:00:00 GMT", "b=2"]
    assert next_url(response["headers"]["Link"]) == "https://x/p2"
    jar = CookieJar().update(response["set_cookie"])
    assert jar.cookie_header() == "a=1; b=2"


def test_credentials_are_dropped_on_an_https_to_http_redirect():
    assert http_client._origin("https://api.x/") != http_client._origin("http://api.x/")
    assert http_client._origin("https://API.x/a") == http_client._origin("https://api.x/b")


def test_an_integer_body_is_refused():
    with pytest.raises(TypeError):
        http_client.build_call("https://x/", "POST", data=5)


def test_decompression_is_bounded_and_errors_are_value_errors():
    bomb = gzip.compress(b"\0" * 100_000)
    with pytest.raises(ValueError, match="exceeds"):
        decode_body({"Content-Encoding": "gzip"}, bomb, max_bytes=1000)
    assert decode_body({"Content-Encoding": "gzip"}, bomb) == b"\0" * 100_000
    two_members = gzip.compress(b"ab") + gzip.compress(b"cd")
    assert decode_body({"Content-Encoding": "gzip"}, two_members) == b"abcd"
    raw_deflate = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    stream = raw_deflate.compress(b"hello") + raw_deflate.flush()
    assert decode_body({"Content-Encoding": "deflate"}, stream) == b"hello"
    with pytest.raises(ValueError):
        decode_body({"Content-Encoding": "gzip"}, b"not gzip")


def test_accept_qvalues_use_qvalue_syntax():
    assert build_accept([("text/html", 0.00001), ("a/b", 0.5)]) == "text/html;q=0, a/b;q=0.5"


def test_a_multipart_name_cannot_inject_a_part():
    evil = 'x"\r\nX-Injected: 1\r\n\r\nevil\r\n--B\r\nContent-Disposition: form-data; name="admin'
    content_type, body = build_multipart([(evil, "v")], boundary="B")
    parsed = parse_multipart(content_type, body)
    assert parsed["fields"] == {evil: "v"}


def test_multipart_values_keep_their_line_breaks_and_quoted_semicolons():
    content_type, body = build_multipart(
        [("note", "line\r\n")],
        [{"name": "f", "filename": "a;b.txt", "content": "hi\n"}], boundary="B")
    parsed = parse_multipart(content_type, body)
    assert parsed["fields"] == {"note": "line\r\n"}
    assert parsed["files"][0]["filename"] == "a;b.txt"
    assert parsed["files"][0]["content"] == "hi\n"


def test_multipart_parsing_accepts_bare_tokens_and_a_capitalised_boundary():
    body = b'--B\r\nContent-Disposition: form-data; name=a\r\n\r\n1\r\n--B--\r\n'
    assert parse_multipart("multipart/form-data; Boundary=B", body)["fields"] == {"a": "1"}


def test_link_parsing_survives_a_quoted_angle_bracket_and_keeps_the_first_rel():
    assert next_url('<https://a/p2>; title="a<b"; rel="next"') == "https://a/p2"
    assert next_url('<https://a/p2>; rel="next"; rel="prev"') == "https://a/p2"
    assert next_url('<https://a/?x=1,2>; rel="next"') == "https://a/?x=1,2"


def test_paginate_resolves_a_relative_next_link():
    pages = {"https://a/items": '</items?page=2>; rel="next"', "https://a/items?page=2": ""}
    seen = []

    def fetch(url):
        seen.append(url)
        return {"headers": {"Link": pages[url]}}

    paginate("https://a/items", fetch)
    assert seen == ["https://a/items", "https://a/items?page=2"]


@pytest.mark.parametrize("url, expected", [
    ("http://[::1]:8080/x", "http://[::1]:8080/x"),
    ("http://:pw@h/", "http://:pw@h/"),
    ("http://h/a/b/..", "http://h/a/"),
    ("http://h/a//b", "http://h/a//b"),
    ("mailto:a@b", "mailto:a@b"),
    ("http://h/?q=%ff&flag", "http://h/?q=%FF&flag"),
    ("HTTP://H:80/./a/%7e", "http://h/a/%7E"),
])
def test_url_normalisation_follows_rfc_3986(url, expected):
    assert normalize_url(url) == expected


def test_empty_path_segments_are_significant():
    assert not urls_equal("http://h/a//b", "http://h/a/b")


def test_an_invalid_max_age_does_not_save_a_deleted_cookie():
    jar = CookieJar({"a": "1"})
    jar.update("a=1; Max-Age=abc; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    assert jar.cookie_header() == ""


def test_an_sse_retry_in_other_digits_is_ignored():
    parser = SSEParser()
    parser.feed("retry: ²\ndata: x\n\n")


def test_a_bare_max_age_is_not_fresh():
    assert is_fresh({"cache_control": {"max-age": True}}, 0) is False


def test_a_null_problem_type_is_about_blank():
    problem = parse_problem({"status": 400, "headers": {"Content-Type": "application/problem+json"},
                             "json": {"type": None, "title": "x"}})
    assert problem is not None and problem.type == "about:blank"
