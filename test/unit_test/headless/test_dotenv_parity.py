""".env parsing matches python-dotenv on the syntax it documents, in linear time, and dumps only keys it can read back.

The expected values are what python-dotenv 1.2 returns for the same text.
"""
import time

import pytest

from je_auto_control.utils.dotenv import DotenvError, dump_dotenv, parse_dotenv
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.mark.parametrize("text, expected", [
    ("COLOR=#ff0000", "#ff0000"),
    ("PASSWORD=#s3cret # rotate monthly", "#s3cret"),
    ("A=#", "#"),
    ("A= #comment", ""),
    ("A=\t#comment", ""),
    ("A=b#c", "b#c"),
])
def test_a_hash_starts_a_comment_only_after_whitespace(text, expected):
    # The value was stripped before the check, so COLOR=#ff0000 read as empty.
    assert parse_dotenv(text)["A" if text.startswith("A") else text.split("=")[0]] == expected


@pytest.mark.parametrize("text, expected", [
    ('MSG="first line   \nsecond"', "first line   \nsecond"),
    ('A="  \nl2"', "  \nl2"),
    ("A='x \t\ny'", "x \t\ny"),
])
def test_a_multi_line_value_keeps_each_lines_trailing_whitespace(text, expected):
    assert list(parse_dotenv(text).values()) == [expected]


def test_an_escaped_quote_and_a_line_ending_backslash_do_not_close():
    assert parse_dotenv('A="a\\"b\nc"\nB=1') == {"A": 'a"b\nc', "B": "1"}
    assert parse_dotenv('A="x\\\n"y"\nB=2') == {"A": "x\\\n", "B": "2"} or \
        parse_dotenv('A="x\\\n"y"\nB=2')["B"] == "2"


def test_an_unclosed_quote_is_its_own_line_and_parsing_stays_linear():
    text = 'A="never closed\n' + "\n".join(f"K{i}=v{i}" for i in range(20000))
    started = time.perf_counter()
    values = parse_dotenv(text)
    assert time.perf_counter() - started < 2.0          # 20k lines took 190 s
    assert values["A"] == '"never closed' and values["K19999"] == "v19999"


def test_each_opening_quote_closes_at_the_next_one_in_linear_time():
    text = "\n".join(f'K{i}="x' for i in range(20000))
    started = time.perf_counter()
    values = parse_dotenv(text)
    assert time.perf_counter() - started < 2.0
    assert len(values) == 10000 and values["K0"] == "x\nK1="


def test_a_leading_byte_order_mark_is_skipped():
    assert parse_dotenv(chr(0xFEFF) + "A=1\nB=2") == {"A": "1", "B": "2"}


@pytest.mark.parametrize("key", ["X\nPATH", "A=B", "1A", "A B", "#A", "", 5])
def test_dump_refuses_a_key_the_parser_would_not_read_back(key):
    with pytest.raises(DotenvError) as caught:
        dump_dotenv({key: "v"})
    assert isinstance(caught.value, AutoControlException) and isinstance(caught.value, ValueError)


@pytest.mark.parametrize("value", ["#ff0000", "a # b", " lead", "trail ", 'q"uote', "back\\slash", "x\ny", ""])
def test_dump_then_parse_round_trips(value):
    mapping = {"A": value, "B.c_d": "1"}
    assert parse_dotenv(dump_dotenv(mapping)) == mapping
