"""Headless tests for CF_HDROP DROPFILES packing (pure byte math; Win32 skipped)."""
import struct

import pytest

import je_auto_control as ac
from je_auto_control.utils.clipboard_files import build_dropfiles, parse_dropfiles


def test_round_trip_wide():
    paths = ["C:\\a\\one.txt", "C:\\b\\twö.png"]  # non-ASCII to exercise UTF-16
    blob = build_dropfiles(paths, point=(12, 34))
    parsed = parse_dropfiles(blob)
    assert parsed["paths"] == paths
    assert parsed["point"] == [12, 34]
    assert parsed["wide"] is True
    assert parsed["non_client"] is False


def test_header_layout_and_double_null():
    blob = build_dropfiles(["a.txt"])
    p_files, x, y, f_nc, f_wide = struct.unpack("<5I", blob[:20])
    assert p_files == 20  # list begins right after the 20-byte header
    assert (x, y, f_nc, f_wide) == (0, 0, 0, 1)
    # wide list ends with two UTF-16 nulls (path-null + list-null)
    assert blob.endswith(b"\x00\x00\x00\x00")


def test_non_wide_uses_single_byte():
    blob = build_dropfiles(["ab.txt"], wide=False)
    assert struct.unpack("<5I", blob[:20])[4] == 0
    parsed = parse_dropfiles(blob)
    assert parsed["paths"] == ["ab.txt"] and parsed["wide"] is False


def test_point_and_non_client_flags():
    parsed = parse_dropfiles(build_dropfiles(["x"], point=(5, 9), non_client=True))
    assert parsed["point"] == [5, 9] and parsed["non_client"] is True


def test_empty_paths_and_short_data_raise():
    with pytest.raises(ValueError):
        build_dropfiles([])
    with pytest.raises(ValueError):
        parse_dropfiles(b"\x00\x00")


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_set_clipboard_files", "AC_get_clipboard_files"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_set_clipboard_files", "ac_get_clipboard_files"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_set_clipboard_files", "AC_get_clipboard_files"} <= specs


def test_facade_exports():
    for name in ("build_dropfiles", "parse_dropfiles",
                 "set_clipboard_files", "get_clipboard_files"):
        assert hasattr(ac, name) and name in ac.__all__
