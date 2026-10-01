"""SSEParser.feed buffers an unterminated line without re-splitting it on every chunk.

Joining and splitting the whole buffer per chunk made one 2 MB ``data`` line
fed in 1 KB chunks take 10.75 s.
"""
import time

from je_auto_control.utils.sse_client import SSEParser


def _feed_all(parser, chunks):
    events = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    return events


def test_a_long_line_in_small_chunks_is_linear():
    payload = "x" * 2_000_000
    stream = f"data: {payload}\n\n"
    parser = SSEParser()
    started = time.perf_counter()
    events = _feed_all(parser, [stream[i:i + 1024] for i in range(0, len(stream), 1024)])
    assert time.perf_counter() - started < 1.0
    assert [event.data for event in events] == [payload]


def test_every_single_character_chunking_gives_the_same_events():
    stream = chr(0xFEFF) + "event: a\r\ndata: 1\r\ndata:2\r\n\r\n: comment\nid: 7\ndata: three\r\r"
    whole = SSEParser().feed(stream)
    parser = SSEParser()
    split = _feed_all(parser, list(stream))
    assert split == whole
    assert [(e.event, e.data, e.id) for e in split] == [("a", "1\n2", None), ("message", "three", "7")]


def test_a_partial_line_is_kept_until_close():
    parser = SSEParser()
    assert _feed_all(parser, ["da", "ta: par", "tial"]) == []
    assert [event.data for event in parser.close()] == ["partial"]
    assert parser.close() == []
