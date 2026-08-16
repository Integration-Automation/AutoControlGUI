"""Headless tests for cross-word OCR matching. No Qt, no screen."""
from dataclasses import dataclass

from je_auto_control.utils.ocr.text_span import (
    LINE_TOLERANCE, find_spans, group_lines, normalize, same_line,
)


@dataclass
class Box:
    """Stand-in for one OCR word box."""
    text: str
    x: int
    y: int
    width: int = 40
    height: int = 20


def _line(*words, y=100, step=50):
    return [Box(text=word, x=10 + index * step, y=y)
            for index, word in enumerate(words)]


def test_normalize_drops_whitespace_and_case():
    # where the engine splits a phrase is arbitrary, so spacing must not decide
    # whether a target matches
    assert normalize(" Save  As ") == "saveas"
    assert normalize("Save As", case_sensitive=True) == "SaveAs"
    assert normalize("") == ""


def test_same_line_uses_vertical_overlap_not_exact_y():
    assert same_line(Box("a", 0, 100), Box("b", 60, 104))
    # a mixed-size row still counts as one line
    assert same_line(Box("a", 0, 100, height=20), Box("B", 60, 98, height=30))
    assert not same_line(Box("a", 0, 100), Box("b", 0, 140))


def test_group_lines_sorts_each_line_left_to_right():
    boxes = [Box("As", 60, 100), Box("Save", 10, 100), Box("File", 10, 200)]
    lines = group_lines(boxes)
    assert [[b.text for b in line] for line in lines] == [["Save", "As"], ["File"]]


def test_find_spans_matches_across_word_boxes():
    # the whole point: "Save As" is two boxes, and per-box matching never sees it
    spans = find_spans(_line("File", "Save", "As", "Later"), "Save As")
    assert [[b.text for b in span] for span in spans] == [["Save", "As"]]


def test_find_spans_matches_cjk_split_by_the_engine():
    spans = find_spans(_line("另存", "新檔"), "另存新檔")
    assert [b.text for b in spans[0]] == ["另存", "新檔"]


def test_find_spans_returns_a_single_box_hit_too():
    # a superset of per-box matching, so nothing that used to match stops
    spans = find_spans(_line("Cancel", "OK"), "OK")
    assert [[b.text for b in span] for span in spans] == [["OK"]]


def test_find_spans_prefers_the_shortest_run():
    spans = find_spans(_line("Save", "As", "PDF"), "Save As")
    assert [b.text for b in spans[0]] == ["Save", "As"]


def test_find_spans_does_not_join_across_lines():
    boxes = [Box("Save", 10, 100), Box("As", 10, 200)]
    assert find_spans(boxes, "Save As") == []


def test_find_spans_reports_each_occurrence_once():
    boxes = _line("OK", "OK")
    assert len(find_spans(boxes, "OK")) == 2


def test_find_spans_is_case_insensitive_by_default():
    assert find_spans(_line("SAVE"), "save")
    assert not find_spans(_line("SAVE"), "save", case_sensitive=True)


def test_find_spans_ignores_an_empty_target():
    assert find_spans(_line("Save"), "   ") == []


def test_find_spans_stops_extending_a_hopeless_run():
    # a long line must not cost a concatenation per (start, end) pair
    boxes = _line(*[f"w{i}" for i in range(200)])
    assert find_spans(boxes, "nothing-here") == []


def test_line_tolerance_is_a_fraction_of_height():
    assert 0 < LINE_TOLERANCE < 1
