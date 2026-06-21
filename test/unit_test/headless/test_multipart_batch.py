"""Headless tests for multipart/form-data build + parse. Pure stdlib, no Qt."""
import base64
import json

import je_auto_control as ac
from je_auto_control.utils.multipart import (
    MultipartFile, build_multipart, new_boundary, parse_multipart,
)

_BOUNDARY = "TESTBOUNDARY123"


def test_build_is_byte_stable_with_fixed_boundary():
    ct, body = build_multipart({"title": "report"}, boundary=_BOUNDARY)
    assert ct == f"multipart/form-data; boundary={_BOUNDARY}"
    assert body == build_multipart({"title": "report"}, boundary=_BOUNDARY)[1]
    assert b'Content-Disposition: form-data; name="title"' in body
    assert b"report" in body
    assert body.endswith(f"--{_BOUNDARY}--\r\n".encode())


def test_build_includes_file_part():
    files = [MultipartFile("upload", "a.txt", "hello", "text/plain")]
    _, body = build_multipart(files=files, boundary=_BOUNDARY)
    assert b'filename="a.txt"' in body
    assert b"Content-Type: text/plain" in body
    assert b"hello" in body


def test_round_trip_fields_and_files():
    files = [{"name": "f", "filename": "data.csv", "content": "a,b\n1,2"}]
    ct, body = build_multipart({"title": "Q3"}, files, boundary=_BOUNDARY)
    parsed = parse_multipart(ct, body)
    assert parsed["fields"] == {"title": "Q3"}
    assert parsed["files"][0]["filename"] == "data.csv"
    assert parsed["files"][0]["content"] == "a,b\n1,2"


def test_field_list_form():
    _, body = build_multipart([("k", "1"), ("k", "2")], boundary=_BOUNDARY)
    assert body.count(b'name="k"') == 2


def test_new_boundary_is_unique():
    assert new_boundary() != new_boundary()


def test_parse_requires_boundary():
    try:
        parse_multipart("application/json", b"{}")
        raised = False
    except ValueError:
        raised = True
    assert raised


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_build_multipart",
        {"fields": json.dumps({"title": "x"}), "boundary": _BOUNDARY}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    body = base64.b64decode(out["body_base64"])
    assert b'name="title"' in body
    rec2 = ac.execute_action([[
        "AC_parse_multipart",
        {"content_type": out["content_type"],
         "body_base64": out["body_base64"]}]])
    parsed = next(v for v in rec2.values() if isinstance(v, dict))
    assert parsed["fields"] == {"title": "x"}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_build_multipart", "AC_parse_multipart"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_build_multipart", "ac_parse_multipart"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_build_multipart", "AC_parse_multipart"} <= specs


def test_facade_exports():
    for attr in ("MultipartFile", "build_multipart", "parse_multipart",
                 "new_boundary"):
        assert hasattr(ac, attr) and attr in ac.__all__
