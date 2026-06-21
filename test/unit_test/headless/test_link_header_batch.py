"""Headless tests for RFC 8288 Link header parsing. Pure stdlib, no Qt."""
import je_auto_control as ac
from je_auto_control.utils.link_header import (
    links_by_rel, next_url, paginate, parse_link_header,
)

_HEADER = ('<https://api.example.com/x?page=2>; rel="next"; title="Page 2", '
           '<https://api.example.com/x?page=9>; rel="last"')


def test_parse_multiple_links_and_params():
    links = parse_link_header(_HEADER)
    assert len(links) == 2
    assert links[0].uri == "https://api.example.com/x?page=2"
    assert links[0].rel == "next" and links[0].params["title"] == "Page 2"
    assert links[1].rel == "last"


def test_links_by_rel_and_next_url():
    indexed = links_by_rel(_HEADER)
    assert set(indexed) == {"next", "last"}
    assert next_url(_HEADER) == "https://api.example.com/x?page=2"
    assert next_url("<https://api/x>; rel=\"prev\"") is None


def test_quoted_value_with_comma():
    header = '<https://api/x>; rel="next"; title="a, b, c"'
    [link] = parse_link_header(header)
    assert link.params["title"] == "a, b, c" and link.rel == "next"


def test_space_separated_rel_indexes_each():
    indexed = links_by_rel('<https://api/x>; rel="next prefetch"')
    assert "next" in indexed and "prefetch" in indexed


def test_empty_header():
    assert parse_link_header("") == [] and next_url("") is None


def test_paginate_follows_next_over_injected_fetch():
    pages = {
        "u1": {"headers": {"Link": '<u2>; rel="next"'}},
        "u2": {"headers": {"Link": '<u3>; rel="next"'}},
        "u3": {"headers": {}},                     # no next → stop
    }
    responses = paginate("u1", lambda url: pages[url])
    assert len(responses) == 3
    assert responses is not None and responses[-1]["headers"] == {}


def test_paginate_respects_max_pages():
    response = {"headers": {"Link": '<self>; rel="next"'}}
    responses = paginate("self", lambda url: response, max_pages=4)
    assert len(responses) == 4


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_parse_link_header", {"value": _HEADER}]])
    links = next(v for v in rec.values() if isinstance(v, dict))["links"]
    assert links[0]["rel"] == "next"
    rec2 = ac.execute_action([["AC_next_url", {"value": _HEADER}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["url"] == \
        "https://api.example.com/x?page=2"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_parse_link_header", "AC_next_url"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_parse_link_header", "ac_next_url"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_parse_link_header", "AC_next_url"} <= specs


def test_facade_exports():
    for attr in ("Link", "parse_link_header", "links_by_rel", "next_url",
                 "paginate"):
        assert hasattr(ac, attr) and attr in ac.__all__
