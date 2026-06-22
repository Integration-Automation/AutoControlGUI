"""Headless tests for W3C Baggage propagation. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.baggage import (
    Baggage, extract_baggage, format_baggage, inject_baggage, parse_baggage,
)


def test_parse_basic_and_metadata():
    bag = parse_baggage("tenant=acme,run=42;meta=x")
    assert bag.get("tenant") == "acme"
    assert bag.get("run") == "42"               # ;metadata stripped
    assert len(bag) == 2


def test_percent_encoding_round_trip():
    bag = Baggage({"key one": "a,b=c"})
    header = format_baggage(bag)
    assert "," not in header.split("=", 1)[1].split("=")[0]  # value encoded
    assert parse_baggage(header).get("key one") == "a,b=c"


def test_immutability_set_and_remove():
    base = Baggage({"a": "1"})
    extended = base.set("b", "2")
    assert "b" not in base and extended.get("b") == "2"
    assert base.remove("a").to_dict() == {} and base.get("a") == "1"


def test_inject_and_extract_case_insensitive():
    bag = Baggage({"tenant": "acme"})
    headers = inject_baggage({"accept": "application/json"}, bag)
    assert headers["baggage"] == "tenant=acme"
    assert headers["accept"] == "application/json"
    assert extract_baggage({"Baggage": "tenant=acme"}).get("tenant") == "acme"


def test_inject_empty_omits_header_and_extract_default():
    assert "baggage" not in inject_baggage({}, Baggage())
    assert extract_baggage({"x": "y"}) == Baggage()


def test_parse_empty_and_malformed():
    assert parse_baggage("") == Baggage()
    assert parse_baggage("nokeyvalue,,=novalue").to_dict() == {}


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_baggage_format", {"items": json.dumps({"tenant": "acme"})}]])
    header = next(v for v in rec.values() if isinstance(v, dict))["header"]
    assert header == "tenant=acme"
    rec2 = ac.execute_action([["AC_baggage_parse", {"header": header}]])
    items = next(v for v in rec2.values() if isinstance(v, dict))["items"]
    assert items == {"tenant": "acme"}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_baggage_parse", "AC_baggage_format"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_baggage_parse", "ac_baggage_format"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_baggage_parse", "AC_baggage_format"} <= specs


def test_facade_exports():
    for attr in ("Baggage", "parse_baggage", "format_baggage",
                 "inject_baggage", "extract_baggage"):
        assert hasattr(ac, attr) and attr in ac.__all__
