"""Headless tests for ICU-lite MessageFormat. No Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.message_format import (
    format_message, ordinal_category, plural_category,
)

_PLURAL = "{count, plural, one {# item} other {# items}}"


def test_simple_placeholder():
    assert format_message("Hello {name}!", {"name": "World"}) == "Hello World!"


def test_plural_one_and_other_with_hash():
    assert format_message(_PLURAL, {"count": 1}) == "1 item"
    assert format_message(_PLURAL, {"count": 5}) == "5 items"


def test_exact_selector_beats_category():
    pattern = "{count, plural, =0 {no items} one {# item} other {# items}}"
    assert format_message(pattern, {"count": 0}) == "no items"
    assert format_message(pattern, {"count": 1}) == "1 item"


def test_select():
    pattern = "{g, select, male {He} female {She} other {They}} won"
    assert format_message(pattern, {"g": "female"}) == "She won"
    assert format_message(pattern, {"g": "nb"}) == "They won"      # other


def test_selectordinal():
    pattern = ("{place, selectordinal, one {#st} two {#nd} few {#rd} "
               "other {#th}}")
    assert format_message(pattern, {"place": 1}) == "1st"
    assert format_message(pattern, {"place": 2}) == "2nd"
    assert format_message(pattern, {"place": 3}) == "3rd"
    assert format_message(pattern, {"place": 11}) == "11th"        # special


def test_offset_adjusts_hash():
    pattern = "{n, plural, offset:1 one {you and # other} other {you and # others}}"
    assert format_message(pattern, {"n": 3}) == "you and 2 others"


def test_nested_select_and_plural():
    pattern = ("{g, select, "
               "male {He has {n, plural, one {# cat} other {# cats}}} "
               "other {They have {n, plural, one {# cat} other {# cats}}}}")
    assert format_message(pattern, {"g": "male", "n": 1}) == "He has 1 cat"
    assert format_message(pattern, {"g": "x", "n": 4}) == "They have 4 cats"


def test_apostrophe_quoting():
    assert format_message("it''s {x} '{lit}'", {"x": "A"}) == "it's A {lit}"


def test_category_helpers():
    assert plural_category(1) == "one"
    assert plural_category(2) == "other"
    assert plural_category(1, locale="fr") == "one"
    assert plural_category(0, locale="fr") == "one"     # French: 0 is "one"
    assert ordinal_category(3) == "few"
    assert ordinal_category(13) == "other"


def test_injectable_rules():
    # always-other rule overrides the locale default
    assert format_message(_PLURAL, {"count": 1},
                          plural_rules=lambda _n: "other") == "1 items"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_format_message",
        {"pattern": _PLURAL, "args": json.dumps({"count": 2})}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["text"] == "2 items"


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_format_message" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_format_message" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_format_message" in specs


def test_facade_exports():
    for attr in ("format_message", "plural_category", "ordinal_category"):
        assert hasattr(ac, attr) and attr in ac.__all__
