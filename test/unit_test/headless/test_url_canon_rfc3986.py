"""URL canonicalisation decodes before it resolves or sorts, keeps empty delimiters, and never invents a host.

RFC 3986 6.2.2: percent-encoding normalisation comes before dot-segment
removal, so ``%2E%2E`` is a ``..``; 6.2.3: ``http://h/?`` is not
``http://h/``; 3.3: a path without an authority cannot begin with ``//``.
"""
import pytest

from je_auto_control.utils.url_canon import canonicalize_url, normalize_url, urls_equal


@pytest.mark.parametrize("url, expected", [
    ("http://h/public/%2E%2E/admin", "http://h/admin"),
    ("http://h/public/%2e%2E/admin", "http://h/admin"),
    ("http://h/a/%2E/b", "http://h/a/b"),
    ("http://h/a/%2e%2e", "http://h/"),
])
def test_an_encoded_dot_segment_is_resolved(url, expected):
    # /public/%2E%2E/admin came out as /public/../admin, which a /public/ prefix allowlist accepted.
    assert canonicalize_url(url) == expected
    assert canonicalize_url(expected) == expected


def test_a_path_that_begins_with_two_slashes_never_becomes_a_host():
    for url in ("http:/a/..//evil.com/", "http:/.//evil.com/"):
        result = canonicalize_url(url)
        assert result == "http:/.//evil.com/"
        assert canonicalize_url(result) == result
        assert not urls_equal(url, "http://evil.com/")


def test_an_authority_that_is_present_but_empty_is_kept():
    assert normalize_url("file:///etc/hosts") == "file:///etc/hosts"
    assert normalize_url("http:/path") == "http:/path"


def test_the_query_is_normalised_before_it_is_sorted():
    assert urls_equal("http://h/?k=%7A&k=b", "http://h/?k=z&k=b")
    assert urls_equal("http://h/?q=%2a&q=%2B", "http://h/?q=%2A&q=%2B")
    once = canonicalize_url("http://h/?k=%7A&k=b")
    assert canonicalize_url(once) == once


def test_an_empty_query_or_fragment_delimiter_is_kept():
    assert normalize_url("http://h/?") == "http://h/?"
    assert normalize_url("http://h/#") == "http://h/#"
    assert normalize_url("http://h/?#") == "http://h/?#"
    assert not urls_equal("http://h/?", "http://h/")


def test_host_escapes_of_unreserved_characters_are_decoded_and_lower_cased():
    assert urls_equal("http://%4A.com/", "http://j.com/")
    assert normalize_url("http://%c3%a9.com/") == "http://%C3%A9.com/"


def test_userinfo_and_fragment_escapes_are_normalised():
    assert normalize_url("http://%7euser@h/#%7efrag") == "http://~user@h/#~frag"
    assert normalize_url("http://User@h/") == "http://User@h/"          # userinfo case is significant


@pytest.mark.parametrize("url, expected", [
    ("HTTP://Example.COM:80/a/./b/../c", "http://example.com/a/c"),
    ("https://h:443", "https://h/"),
    ("mailto:a@b", "mailto:a@b"),
    ("http://[::1]:8080/x", "http://[::1]:8080/x"),
    ("//h/a/../b", "//h/b"),
])
def test_existing_normalisations_still_hold(url, expected):
    assert normalize_url(url) == expected
