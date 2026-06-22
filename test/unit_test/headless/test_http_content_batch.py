"""Headless tests for HTTP content negotiation + decoding. No Qt."""
import base64
import gzip
import json
import zlib

import pytest

import je_auto_control as ac
from je_auto_control.utils.http_content import (
    build_accept, build_accept_encoding, decode_body, negotiated_call,
    parse_quality_values,
)


def test_build_accept_with_and_without_quality():
    assert build_accept(["application/json"]) == "application/json"
    header = build_accept([("application/json", 1.0), ("text/html", 0.8)])
    assert header == "application/json, text/html;q=0.8"


def test_build_accept_encoding_default_and_custom():
    assert build_accept_encoding() == "gzip, deflate"
    assert build_accept_encoding(["identity"]) == "identity"


def test_parse_quality_values_sorted_by_q():
    parsed = parse_quality_values("text/html;q=0.8, application/json, text/*;q=0.1")
    assert parsed[0] == ("application/json", 1.0)
    assert parsed[-1] == ("text/*", 0.1)


def test_decode_gzip_and_deflate_and_identity():
    payload = b"hello world payload"
    assert decode_body({"Content-Encoding": "gzip"},
                       gzip.compress(payload)) == payload
    assert decode_body({"content-encoding": "deflate"},
                       zlib.compress(payload)) == payload
    assert decode_body({}, payload) == payload
    assert decode_body({"Content-Encoding": "identity"}, payload) == payload


def test_decode_raw_deflate_fallback():
    payload = b"raw deflate stream"
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = compressor.compress(payload) + compressor.flush()
    assert decode_body({"Content-Encoding": "deflate"}, raw) == payload


def test_decode_unsupported_raises():
    with pytest.raises(ValueError):
        decode_body({"Content-Encoding": "br"}, b"...")


def test_negotiated_call_sets_headers():
    call = {"url": "https://api/x", "headers": {"accept": "x"}}
    out = negotiated_call(call, accept="application/json")
    assert out["headers"]["Accept"] == "application/json"
    assert out["headers"]["Accept-Encoding"] == "gzip, deflate"
    assert call["headers"] == {"accept": "x"}        # input untouched


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    body = base64.b64encode(gzip.compress(b"data")).decode()
    rec = ac.execute_action([[
        "AC_decode_body",
        {"headers": json.dumps({"Content-Encoding": "gzip"}),
         "body_base64": body}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["text"] == "data"
    rec2 = ac.execute_action([[
        "AC_parse_quality_values", {"header": "a;q=0.2, b"}]])
    values = next(v for v in rec2.values() if isinstance(v, dict))["values"]
    assert values[0] == ["b", 1.0]


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_decode_body", "AC_parse_quality_values"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_decode_body", "ac_parse_quality_values"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_decode_body", "AC_parse_quality_values"} <= specs


def test_facade_exports():
    for attr in ("build_accept", "build_accept_encoding", "decode_body",
                 "negotiated_call", "parse_quality_values"):
        assert hasattr(ac, attr) and attr in ac.__all__
