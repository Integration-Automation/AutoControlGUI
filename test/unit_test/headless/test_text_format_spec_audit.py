"""Text-format helpers follow their references at the edges.

ICU MessageFormat quoting, ``offset: 1`` and infinite counts; French ``many``
(CLDR); ``.mo`` catalogues in a non-UTF-8 charset (GNU gettext); single-quote
escapes in ``.env`` (python-dotenv); JSON-pointer ``$ref`` tokens
(RFC 6901); a ``;`` inside an SQL literal; ``Infinity`` in ``parse_number``.
"""
import sqlite3
import struct

import pytest

from je_auto_control.utils.data_source.data_source import _validate_select
from je_auto_control.utils.dotenv.dotenv import parse_dotenv
from je_auto_control.utils.exception.exceptions import AutoControlJsonException
from je_auto_control.utils.gettext_catalog.gettext_catalog import read_mo
from je_auto_control.utils.json_schema.json_schema import validate_json
from je_auto_control.utils.message_format.message_format import format_message, plural_category
from je_auto_control.utils.sql.sql_query import query_sqlite


def test_an_apostrophe_quotes_hash_only_inside_a_plural():
    assert format_message("Use '#' or '|' here") == "Use '#' or '|' here"
    assert format_message("{n, plural, other {'#' is #}}", {"n": 3}) == "# is 3"
    assert format_message("'{literal}'") == "{literal}"


def test_offset_may_be_followed_by_a_space():
    pattern = "{n, plural, offset: 1 =0 {none} one {you and # other} other {you and # others}}"
    assert format_message(pattern, {"n": 3}) == "you and 2 others"


def test_an_infinite_count_is_a_value_error():
    with pytest.raises(ValueError, match="not a number"):
        format_message("{n, plural, other {#}}", {"n": float("inf")})


def test_french_millions_are_many():
    assert plural_category(1_000_000, "fr") == "many"
    assert plural_category(2_000_000, "fr") == "many"
    assert plural_category(1_000_001, "fr") == "other"
    assert plural_category(1, "fr") == "one"


def _mo(pairs):
    pairs = sorted(pairs)
    count = len(pairs)
    orig_off, trans_off = 28, 28 + 8 * count
    data_off = trans_off + 8 * count
    blob, orig_table, trans_table = b"", b"", b""
    for original, _ in pairs:
        orig_table += struct.pack("<II", len(original), data_off + len(blob))
        blob += original + b"\0"
    for _, translation in pairs:
        trans_table += struct.pack("<II", len(translation), data_off + len(blob))
        blob += translation + b"\0"
    header = struct.pack("<IIIIIII", 0x950412DE, 0, count, orig_off, trans_off, 0, 0)
    return header + orig_table + trans_table + blob


def test_a_latin1_mo_catalogue_is_read_in_its_charset():
    data = _mo([(b"", b"Content-Type: text/plain; charset=ISO-8859-1\n"),
                (b"coffee", "café".encode("latin-1"))])
    assert read_mo(data).gettext("coffee") == "café"


def test_single_quoted_dotenv_values_decode_their_two_escapes():
    parsed = parse_dotenv("A='it\\'s'\nB='a\\\\b'\nC='C:\\path'\n")
    assert parsed == {"A": "it's", "B": "a\\b", "C": "C:\\path"}


def test_ref_tokens_follow_rfc_6901():
    schema = {"$defs": {"seq": [{"type": "string"}], "a b": {"type": "integer"}}}
    assert validate_json("x", {**schema, "$ref": "#/$defs/seq/0"}).ok
    with pytest.raises(AutoControlJsonException):
        validate_json("x", {**schema, "$ref": "#/$defs/seq/" + chr(0xB2)})
    with pytest.raises(AutoControlJsonException):
        validate_json("x", {**schema, "$ref": "#/$defs/seq/00"})
    assert not validate_json("x", {**schema, "$ref": "#/$defs/a%20b"}).ok
    assert validate_json(5, {**schema, "$ref": "#/$defs/a%20b"}).ok


def test_a_semicolon_inside_a_literal_is_one_statement(tmp_path):
    path = tmp_path / "t.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (n TEXT)")
        conn.execute("INSERT INTO t VALUES ('a;b')")
    conn.close()
    assert query_sqlite(str(path), "SELECT n FROM t WHERE n = 'a;b'") == [{"n": "a;b"}]
    assert _validate_select("SELECT 'it''s; fine' -- a; comment\n") == "SELECT 'it''s; fine' -- a; comment"
    with pytest.raises(ValueError, match="single statement"):
        _validate_select("SELECT 1; DROP TABLE t")
    with pytest.raises(ValueError, match="single statement"):
        _validate_select("SELECT ';' ; SELECT 2")


def test_parse_number_refuses_infinity():
    pytest.importorskip("babel")
    from je_auto_control.utils.locale_parse.locale_parse import parse_number
    with pytest.raises(ValueError):
        parse_number("Infinity")
    assert parse_number("1,234") == 1234
