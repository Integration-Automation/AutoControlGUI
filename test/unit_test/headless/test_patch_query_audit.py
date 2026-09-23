"""Regression tests for the JSON Patch, JSONPath and unified-diff defects of the 2026-09-23 audit.

``add`` refused an index equal to the array length, shared its value with the
caller's patch, and ``move`` onto itself skipped the existence check. JSONPath
turned a filter it could not read into a wildcard, treated ``true`` as ``1``,
split ``foo-bar`` and dropped an unterminated ``[``. ``apply_unified`` put
``-N,0`` insertions one line early, lost body lines starting with ``---`` /
``+++`` and failed on ``\\ No newline`` markers; ``three_way_merge`` kept two
different insertions at one point, and duplicated an identical one.
"""
import random

import pytest

from je_auto_control.utils.json_patch.json_patch import PatchError, apply_patch
from je_auto_control.utils.jsonpath import json_query
from je_auto_control.utils.text_diff.text_diff import apply_unified, three_way_merge, unified_diff


def test_add_may_insert_at_the_array_length():
    assert apply_patch({"a": [1, 2]}, [{"op": "add", "path": "/a/2", "value": 3}]) == {"a": [1, 2, 3]}


def test_add_does_not_share_its_value_with_the_patch():
    patch = [{"op": "add", "path": "/x", "value": {}}, {"op": "add", "path": "/x/k", "value": 1}]
    result = apply_patch({}, patch)
    assert patch[0]["value"] == {} and result == {"x": {"k": 1}}


def test_move_onto_itself_still_needs_the_source():
    with pytest.raises(PatchError):
        apply_patch({}, [{"op": "move", "from": "/nope", "path": "/nope"}])


@pytest.mark.parametrize("index", ["\u00b2", "\u0661"])
def test_array_indexes_are_ascii_digits(index):
    with pytest.raises(PatchError):
        apply_patch({"a": [0, 1, 2]}, [{"op": "remove", "path": f"/a/{index}"}])


_ITEMS = {"items": [{"a": {"b": 1}, "n": 0, "flag": True}, {"a": {"b": 2}, "flag": 1}, {"x": 1}]}


def test_a_nested_filter_path_selects_only_matches():
    assert json_query(_ITEMS, "$.items[?(@.a.b == 1)]") == [_ITEMS["items"][0]]


def test_an_existence_filter_selects_items_that_have_the_key():
    assert json_query(_ITEMS, "$.items[?(@.n)]") == [_ITEMS["items"][0]]


def test_true_is_not_equal_to_one():
    assert json_query(_ITEMS, "$.items[?(@.flag == 1)]") == [_ITEMS["items"][1]]


def test_a_bare_key_may_contain_a_dash():
    assert json_query({"foo-bar": 1, "foo": {"bar": "wrong"}}, "$.foo-bar") == [1]


def test_a_quoted_key_may_contain_a_bracket():
    assert json_query({"a]b": 5}, "$['a]b']") == [5]


@pytest.mark.parametrize("path", ["$.items[0", "$.items[?(@.a =~ 1)]", "$.a b"])
def test_an_unreadable_path_is_an_error(path):
    with pytest.raises(ValueError):
        json_query(_ITEMS, path)


def test_a_pure_insertion_hunk_goes_after_its_line():
    assert apply_unified("a\nb\nc\n", "@@ -0,0 +1 @@\n+new") == "new\na\nb\nc\n"
    assert apply_unified("a\nb\nc\n", "@@ -2,0 +3 @@\n+INS") == "a\nb\nINS\nc\n"


@pytest.mark.parametrize("before, after", [("x\n-- comment\ny\n", "x\ny\n"), ("x\ny\n", "x\n++z\ny\n")])
def test_body_lines_that_look_like_headers_are_applied(before, after):
    assert apply_unified(before, unified_diff(before, after)) == after


def test_a_no_newline_marker_is_skipped():
    diff = ("--- a\n+++ b\n@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n"
            "+c\n\\ No newline at end of file")
    assert apply_unified("a\nb", diff) == "a\nc"


def test_zero_context_diffs_round_trip():
    rng = random.Random(1)
    for _ in range(500):
        before = "".join(f"{rng.choice('abcde')}\n" for _ in range(rng.randint(0, 8)))
        after = "".join(f"{rng.choice('abcde')}\n" for _ in range(rng.randint(0, 8)))
        patched = apply_unified(before, unified_diff(before, after, context=0))
        assert patched.splitlines() == after.splitlines()   # final newline follows the source


def test_two_insertions_at_one_point_conflict():
    assert not three_way_merge("1\n2\n3\n", "1\nA\n2\n3\n", "1\nB\n2\n3\n").clean


def test_an_identical_change_on_both_sides_is_applied_once():
    merged = three_way_merge("1\n2\n3\n", "1\nI\n2\n3\n", "1\nI\n2\n3\nZ\n")
    assert merged.clean and merged.text == "1\nI\n2\n3\nZ\n"
