"""multipart/form-data keeps its boundary out of every part, validates it, and reads only that parameter.

RFC 2046 5.1.1: the delimiter must not appear inside an encapsulated part, and
a boundary is 1-70 characters from a fixed set.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.multipart.multipart import (
    MultipartError, build_multipart, new_boundary, parse_multipart,
)

INJECTION = 'x\r\n--B\r\nContent-Disposition: form-data; name="evil"\r\n\r\ninjected'


def test_a_value_that_contains_the_callers_boundary_is_refused():
    # It used to parse back as two fields, one of them chosen by the value.
    with pytest.raises(MultipartError):
        build_multipart({"a": INJECTION}, boundary="B")
    with pytest.raises(MultipartError):
        build_multipart(files=[{"name": "f", "filename": "a.txt", "content": b"--B\r\n"}], boundary="B")


def test_a_generated_boundary_avoids_the_content(monkeypatch):
    from je_auto_control.utils.multipart import multipart
    tokens = iter(["taken", "free"])
    monkeypatch.setattr(multipart, "new_boundary", lambda: next(tokens))
    content_type, body = build_multipart({"a": "x\r\n--taken"})
    assert content_type == "multipart/form-data; boundary=free"
    assert parse_multipart(content_type, body)["fields"] == {"a": "x\r\n--taken"}


@pytest.mark.parametrize("boundary", ["B\r\nX-Injected: 1", "x" * 71, "ends in space ", "semi;colon", "q\"uote"])
def test_a_boundary_rfc_2046_does_not_allow_is_refused(boundary):
    with pytest.raises(MultipartError) as caught:
        build_multipart({"a": "1"}, boundary=boundary)
    assert isinstance(caught.value, AutoControlException) and isinstance(caught.value, ValueError)


@pytest.mark.parametrize("boundary, parameter", [("simple-B_1.x", "simple-B_1.x"), ("with space", '"with space"'),
                                                 ("a:b=c?", '"a:b=c?"'), ("x" * 70, "x" * 70)])
def test_an_allowed_boundary_round_trips_and_is_quoted_when_it_must_be(boundary, parameter):
    content_type, body = build_multipart({"k": "v"}, boundary=boundary)
    assert content_type == f"multipart/form-data; boundary={parameter}"
    assert parse_multipart(content_type, body)["fields"] == {"k": "v"}


def test_only_the_boundary_parameter_is_read():
    content_type, body = build_multipart({"k": "v"}, boundary="real")
    assert parse_multipart("multipart/form-data; notboundary=x; boundary=real", body)["fields"] == {"k": "v"}


def test_a_missing_boundary_is_a_multipart_error():
    with pytest.raises(MultipartError):
        parse_multipart("multipart/form-data", b"")


def test_the_default_boundary_is_valid():
    assert build_multipart({"k": "v"}, boundary=new_boundary())[0].startswith("multipart/form-data; boundary=----")
