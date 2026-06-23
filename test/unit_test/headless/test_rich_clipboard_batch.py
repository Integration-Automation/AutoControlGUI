"""Headless tests for rich (CF_HTML) clipboard. No Qt; I/O is Windows-only."""
import re
import sys

import pytest

import je_auto_control as ac
from je_auto_control.utils.rich_clipboard import (
    build_cf_html, get_clipboard_html, parse_cf_html, set_clipboard_html,
)


def test_build_offsets_point_at_fragment():
    html = "<b>Bold</b> & <i>café</i> 文字"   # multibyte UTF-8
    blob = build_cf_html(html)
    assert isinstance(blob, bytes)
    text = blob.decode("utf-8")
    start = int(re.search(r"StartFragment:(\d+)", text).group(1))
    end = int(re.search(r"EndFragment:(\d+)", text).group(1))
    assert blob[start:end].decode("utf-8") == html       # byte offsets are exact


def test_round_trip_via_markers():
    html = "<p>hello <b>world</b></p>"
    assert parse_cf_html(build_cf_html(html)) == html


def test_parse_marker_only_payload():
    payload = "<html><body><!--StartFragment-->X<!--EndFragment--></body></html>"
    assert parse_cf_html(payload) == "X"


def test_parse_offset_fallback_without_markers():
    fragment = "FRAG"
    body = "<html>" + fragment + "</html>"
    prefix = "StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n".format(
        len("<html>"), len("<html>") + len(fragment))
    # offsets are relative to the whole payload, so prepend the header length
    header_len = len(prefix.encode("utf-8"))
    payload = ("StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n".format(
        header_len + len("<html>"), header_len + len("<html>") + len(fragment))
        + body).encode("utf-8")
    assert parse_cf_html(payload) == fragment


def test_build_rejects_non_string():
    with pytest.raises(TypeError):
        build_cf_html(b"bytes")


@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="HTML clipboard I/O is supported on Windows")
def test_io_raises_off_windows():
    with pytest.raises(RuntimeError):
        set_clipboard_html("<b>x</b>")
    with pytest.raises(RuntimeError):
        get_clipboard_html()


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_set_clipboard_html", "AC_get_clipboard_html"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_set_clipboard_html", "ac_get_clipboard_html"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_set_clipboard_html", "AC_get_clipboard_html"} <= specs


def test_facade_exports():
    for attr in ("build_cf_html", "parse_cf_html", "get_clipboard_html",
                 "set_clipboard_html"):
        assert hasattr(ac, attr) and attr in ac.__all__
