"""JSONPath, OCR-structure and codec defects from the 2026-09-24 audit (no screen, no network).

A quoted union was read as one odd key and a lone quote as a string; a
parenless filter broke when a later filter used ")]"; escapes in quoted
names were not decoded; booleans and null were ordered the Python way;
min_table_rows=0 crashed; a label with nothing to its right took the next
row's first cell.
"""
import types

import pytest

from je_auto_control.utils.jsonpath.jsonpath import json_query
from je_auto_control.utils.ocr.ocr_engine import TextMatch
from je_auto_control.utils.ocr.structure import cluster_matches


@pytest.mark.parametrize("path", ["$['a','b']", "$[?(@.k == ')]", "$[?(@.k == 'ab\")]", "$['a"])
def test_malformed_quotes_raise(path):
    with pytest.raises(ValueError):
        json_query({"a": 1, "b": 2, "a','b": "WRONG"}, path)


def test_quoted_names_decode_their_escapes():
    data = {"a'b": 1, "a\\'b": 2, "a]b": 3, "é": 4}
    assert json_query(data, "$['a\\'b']") == [1]
    assert json_query(data, "$['a]b']") == [3]
    assert json_query(data, "$['\\u00e9']") == [4]


def test_a_parenless_filter_before_a_parenthesised_one():
    data = {"x": [{"a": 1, "b": {"z": [{"c": 1}, {"d": 2}]}}, {"a": 2}]}
    assert json_query(data, "$.x[?@.a==1].b.z[?(@.c)]") == [{"c": 1}]


def test_ordering_follows_rfc_9535():
    assert json_query([{"k": False}], "$[?(@.k < true)]") == []
    assert json_query([{"k": None}], "$[?(@.k <= null)]") == [{"k": None}]
    assert json_query([{"k": 1}, {"k": 2}], "$[?(@.k >= 2)]") == [{"k": 2}]
    assert json_query([{"k": "b"}], "$[?(@.k > 'a')]") == [{"k": "b"}]
    assert json_query([{"k": 1}], "$[?(@.k > 'a')]") == []


def _match(text, x, y, width=60, height=20):
    return TextMatch(text, x, y, width, height, 95.0)


def test_zero_minimum_table_rows_does_not_crash():
    cluster_matches([_match("a", 0, 0), _match("b", 100, 0)], min_table_rows=0)


def test_a_label_takes_the_cell_below_it():
    matches = [_match("Name:", 0, 0), _match("Age:", 300, 0),
               _match("Bob", 0, 40), _match("42", 300, 40)]
    values = {field.label: field.value for field in cluster_matches(matches).fields}
    assert values.get("Age") == "42"
    assert values.get("Name") == "Bob"


class _FakeContext:
    """A CodecContext stand-in whose ``open`` fails for the names in ``refuse``."""

    refuse: tuple = ()

    def __init__(self, name):
        self.name = name

    def open(self):
        if self.name in self.refuse:
            raise ValueError("avcodec_open2 failed")


def _fake_create(monkeypatch, hw_codec, refuse):
    created = []

    def create(name, _mode):
        context = _FakeContext(name)
        context.refuse = refuse
        created.append(context)
        return context

    # CodecContext is an immutable extension type, so the module is swapped.
    fake_av = types.SimpleNamespace(CodecContext=types.SimpleNamespace(create=create),
                                    FFmpegError=hw_codec.av.FFmpegError)
    monkeypatch.setattr(hw_codec, "av", fake_av)
    return created


def test_hardware_codecs_are_listed_only_when_they_open(monkeypatch):
    pytest.importorskip("av")
    from je_auto_control.utils.remote_desktop import hw_codec
    _fake_create(monkeypatch, hw_codec, refuse=("h264_qsv",))
    listed = hw_codec.available_hardware_codecs()
    assert "h264_qsv" not in listed and "h264_nvenc" in listed


def test_an_encoder_that_cannot_open_falls_back_to_libx264(monkeypatch):
    pytest.importorskip("av")
    from je_auto_control.utils.remote_desktop import hw_codec

    class _Frame:
        width, height = 640, 480

    created = _fake_create(monkeypatch, hw_codec, refuse=("h264_qsv",))
    context = hw_codec._open_codec_context("h264_qsv", _Frame(), 1_000_000, 30)
    assert context.name == "libx264" and [c.name for c in created] == ["h264_qsv", "libx264"]
    nvenc = hw_codec._open_codec_context("h264_nvenc", _Frame(), 1_000_000, 30)
    assert nvenc.options.get("tune") != "zerolatency"   # NVENC refuses to open with it


def _libx264_available() -> bool:
    av = pytest.importorskip("av")
    try:
        av.codec.Codec("libx264", "w")
    except (ValueError, av.FFmpegError):
        return False
    return True


def test_odd_frame_sizes_encode():
    if not _libx264_available():
        pytest.skip("this PyAV build has no libx264")
    import io
    from PIL import Image
    from je_auto_control.utils.remote_desktop.video_codec import H264CodecProvider

    def jpeg(width, height):
        buffer = io.BytesIO()
        Image.new("RGB", (width, height), (10, 200, 30)).save(buffer, "JPEG")
        return buffer.getvalue()

    provider = H264CodecProvider()
    try:
        packets = [packet for size in ((101, 75), (101, 75), (120, 90), (1, 1))
                   for packet in provider.encode_jpeg(jpeg(*size))]
        assert packets
    finally:
        provider.close()


def test_close_closes_the_container_when_the_flush_fails():
    av = pytest.importorskip("av")
    from je_auto_control.utils.remote_desktop.video_codec import H264CodecProvider
    closed = []

    class _Stream:
        def encode(self, _frame):
            raise av.error.ExternalError(-1, "avcodec_open2(libx264)")

    class _Container:
        def close(self):
            closed.append(True)

    provider = H264CodecProvider()
    provider._stream, provider._container = _Stream(), _Container()
    provider.close()
    assert closed == [True]
