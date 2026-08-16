"""Headless tests for RFC 3986 URL canonicalisation. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.url_canon import (
    build_query, canonicalize_url, normalize_url, parse_query, urls_equal,
)


def test_canonicalize_lowercases_and_collapses():
    assert canonicalize_url("HTTP://Example.COM:80/a/./b/../c?b=2&a=1#frag") == \
        "http://example.com/a/c?a=1&b=2"


def test_normalize_default_port_and_percent_case():
    assert normalize_url("https://EXAMPLE.com:443/p%2fx/") == \
        "https://example.com/p%2Fx/"


def test_empty_path_becomes_root():
    assert normalize_url("http://host") == "http://host/"


def test_dot_segments_beyond_root_clamped():
    assert canonicalize_url("http://h/../../x") == "http://h/x"


def test_urls_equal_ignores_query_order_and_fragment():
    assert urls_equal("http://x.com/a?b=1&a=2",
                      "http://x.com/a?a=2&b=1#top") is True
    assert urls_equal("http://x.com/a", "http://x.com/b") is False


def test_build_and_parse_query():
    assert build_query({"q": "hello world", "p": 2}, sort=True) == \
        "p=2&q=hello+world"
    assert parse_query("a=1&b=&c=3") == [("a", "1"), ("b", ""), ("c", "3")]
    assert parse_query("a=1&b=", keep_blank=False) == [("a", "1")]


def test_userinfo_preserved():
    assert normalize_url("http://User:Pass@Host.COM/") == \
        "http://User:Pass@host.com/"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_canonicalize_url", {"url": "HTTP://A.com:80/x/../y"}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["url"] == "http://a.com/y"
    rec2 = ac.execute_action([[
        "AC_urls_equal",
        {"first": "http://x/a?b=1&a=2", "second": "http://x/a?a=2&b=1"}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["equal"] is True


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_canonicalize_url", "AC_urls_equal"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_canonicalize_url", "ac_urls_equal"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_canonicalize_url", "AC_urls_equal"} <= specs


def test_facade_exports():
    for attr in ("canonicalize_url", "normalize_url", "urls_equal",
                 "build_query", "parse_query"):
        assert hasattr(ac, attr) and attr in ac.__all__
