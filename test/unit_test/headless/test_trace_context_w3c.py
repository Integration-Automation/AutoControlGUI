"""tracestate follows the W3C Trace Context grammar, and nothing invalid reaches an outgoing header.

Cases from the W3C trace-context test suite (``test/test.py``) and the REC's
3.3.1.3.2 value grammar.
"""
import time

import pytest

from je_auto_control.utils.trace_context import (
    SpanContext, TraceContextError, child_context, format_tracestate, format_traceparent,
    inject_context, parse_traceparent, parse_tracestate,
)

TRACE = "12345678901234567890123456789012"
SPAN = "1234567890123456"


def test_a_value_keeps_its_leading_spaces():
    # value = 0*255(chr) nblk-chr, and chr includes SP; they were stripped.
    assert parse_tracestate("foo=  bar") == [("foo", "  bar")]
    assert parse_tracestate(" foo=bar ,\tbaz=1\t") == [("foo", "bar"), ("baz", "1")]


@pytest.mark.parametrize("header", [
    "foo=", "foo=bar=baz", "foo=a" + chr(0x7F) + "b", "foo=caf" + chr(0xE9),
    "foo=" + "x" * 257, "foo=a\r\nX-Injected: 1", "foo =bar",
])
def test_a_member_that_breaks_the_value_grammar_is_discarded(header):
    assert parse_tracestate(header + ",bar=2") == [("bar", "2")]


def test_the_longest_value_is_256_characters():
    assert parse_tracestate("foo=" + "x" * 256) == [("foo", "x" * 256)]


def test_parsing_stops_after_32_members_and_stays_linear():
    header = ",".join(f"k{i}=v" for i in range(20000))
    started = time.perf_counter()
    items = parse_tracestate(header)
    assert len(items) == 32 and items[0] == ("k0", "v")
    assert time.perf_counter() - started < 1.0          # 16k members took 6.4 s


def test_a_duplicated_key_still_invalidates_the_header():
    assert parse_tracestate("foo=1,bar=2,foo=3") == []


@pytest.mark.parametrize("items", [
    [("foo", "a\r\nX-Injected: 1")], [("Foo", "1")], [("foo", "")], [("foo", "a,b")], [("foo", 1)],
])
def test_an_invalid_member_never_reaches_an_outgoing_header(items):
    with pytest.raises(TraceContextError):
        format_tracestate(items)
    with pytest.raises(TraceContextError):
        inject_context({}, SpanContext(TRACE, SPAN, 1, items))


@pytest.mark.parametrize("ctx", [
    SpanContext(TRACE + "\r\nX: 1", SPAN), SpanContext(TRACE, "zz" * 8), SpanContext("0" * 32, SPAN),
    SpanContext(TRACE, SPAN, 256), SpanContext(TRACE, SPAN, -1), SpanContext(TRACE, SPAN, True),
])
def test_a_hand_built_context_is_validated_before_it_is_written(ctx):
    with pytest.raises(TraceContextError):
        format_traceparent(ctx)


def test_a_valid_context_round_trips():
    ctx = SpanContext(TRACE, SPAN, 1, [("vendor", " x y"), ("t@sys", "1")])
    headers = inject_context({}, ctx)
    assert headers == {"traceparent": f"00-{TRACE}-{SPAN}-01", "tracestate": "vendor= x y,t@sys=1"}
    assert parse_tracestate(headers["tracestate"]) == ctx.tracestate


def test_a_child_clears_the_flag_bits_nobody_defined():
    parent = parse_traceparent(f"00-{TRACE}-{SPAN}-ff")
    assert child_context(parent).trace_flags == 0x03


@pytest.mark.parametrize("header", [f"\n00-{TRACE}-{SPAN}-01", f"00-{TRACE}-{SPAN}-01\r\n",
                                    chr(0xA0) + f"00-{TRACE}-{SPAN}-01"])
def test_traceparent_trims_only_spaces_and_tabs(header):
    with pytest.raises(TraceContextError):
        parse_traceparent(header)
    assert parse_traceparent(f" \t00-{TRACE}-{SPAN}-01\t").trace_id == TRACE
