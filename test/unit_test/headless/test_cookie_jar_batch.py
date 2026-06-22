"""Headless tests for the RFC 6265 cookie jar. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.cookie_jar import CookieJar, parse_set_cookie


def test_parse_set_cookie():
    parsed = parse_set_cookie("sid=abc123; Path=/; Max-Age=3600; HttpOnly")
    assert parsed["name"] == "sid" and parsed["value"] == "abc123"
    assert parsed["attributes"]["path"] == "/"
    assert parsed["attributes"]["max-age"] == "3600"
    assert parsed["attributes"]["httponly"] == ""
    assert parse_set_cookie("novalue") is None


def test_update_and_cookie_header():
    jar = CookieJar().update(["sid=abc; Path=/", "theme=dark"])
    assert len(jar) == 2
    header = jar.cookie_header()
    assert "sid=abc" in header and "theme=dark" in header
    assert "; " in header


def test_single_string_update():
    jar = CookieJar().update("token=xyz; Secure")
    assert jar.to_dict() == {"token": "xyz"}


def test_expired_or_empty_removes_cookie():
    jar = CookieJar({"sid": "abc"})
    jar.update("sid=; Max-Age=0")
    assert "sid" not in jar.to_dict()
    jar.set("a", "1").update("a=; Max-Age=-1")
    assert "a" not in jar.to_dict()


def test_set_and_dict_round_trip():
    jar = CookieJar().set("k", "v")
    restored = CookieJar.from_dict(jar.to_dict())
    assert restored.to_dict() == {"k": "v"}


def test_save_and_load(tmp_path):
    path = str(tmp_path / "jar.json")
    CookieJar({"sid": "abc"}).save(path)
    assert CookieJar.load(path).cookie_header() == "sid=abc"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_cookie_header",
        {"set_cookies": json.dumps(["sid=abc", "t=1"])}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["cookies"] == {"sid": "abc", "t": "1"}
    rec2 = ac.execute_action([[
        "AC_parse_set_cookie", {"header": "sid=abc; Path=/"}]])
    cookie = next(v for v in rec2.values() if isinstance(v, dict))["cookie"]
    assert cookie["name"] == "sid"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_cookie_header", "AC_parse_set_cookie"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_cookie_header", "ac_parse_set_cookie"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_cookie_header", "AC_parse_set_cookie"} <= specs


def test_facade_exports():
    for attr in ("CookieJar", "parse_set_cookie"):
        assert hasattr(ac, attr) and attr in ac.__all__
