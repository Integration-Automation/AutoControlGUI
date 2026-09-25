"""Small utility defects from the 2026-09-24 audit (pure functions; no desktop).

A zero-weight grounding candidate divided by zero; table cells and borderless
rows joined their words out of reading order; one ``inf`` aborted a data
profile; an unknown verify mode compared exactly; accent position and NFD input
were lost in collation; ``parse_cf_html`` skipped its offset fallback for str;
a superscript digit crashed role parsing; out-of-range HSV bounds overflowed.
"""
import numpy as np
import pytest


def test_zero_weight_candidates_do_not_divide_by_zero():
    from je_auto_control.utils.grounding_consensus.grounding_consensus import (
        consensus_element, consensus_point,
    )
    mixed = consensus_point([{"x": 10, "y": 10, "weight": 0.0},
                             {"x": 500, "y": 500, "weight": 1.0}])
    assert mixed.point == [500, 500] and mixed.agreement == 1.0
    silent = consensus_point([{"x": 10, "y": 10, "weight": 0},
                              {"x": 12, "y": 12, "weight": 0},
                              {"x": 400, "y": 400, "weight": 0}])
    assert silent.point == [11, 11] and silent.n_clusters == 2
    winner, agreement = consensus_element([{"x": 10, "y": 10, "weight": 0.0}],
                                          [{"x": 0, "y": 0, "width": 20, "height": 20}])
    assert winner["width"] == 20 and agreement == 1.0
    with pytest.raises(ValueError):
        consensus_point([[1, 1, float("nan")]])
    with pytest.raises(ValueError):
        consensus_point([[1, 1, -1]])


def _word(x, y, text, width=40, height=20):
    return {"x": x, "y": y, "width": width, "height": height, "text": text}


def test_a_two_line_cell_reads_line_by_line():
    from je_auto_control.utils.table_grid_fill.table_grid_fill import assign_text_to_grid
    boxes = [_word(10, 10, "Hello"), _word(60, 12, "world"), _word(10, 40, "foo")]
    assert assign_text_to_grid({"cols": [0, 200], "rows": [0, 100]}, boxes) == [
        ["Hello world foo"]]


def test_words_in_one_borderless_cell_read_left_to_right():
    from je_auto_control.utils.column_layout.column_layout import detect_borderless_table
    boxes = [_word(45, 0, "Doe", 30), _word(0, 0, "John"), _word(200, 0, "30", 30),
             _word(0, 30, "Ann"), _word(200, 30, "41", 30)]
    assert detect_borderless_table(boxes)["rows"] == [["John Doe", "30"], ["Ann", "41"]]


def test_a_profile_survives_non_finite_numbers():
    from je_auto_control.utils.data_profile.data_profile import infer_schema, profile_rows
    rows = [{"v": 1.0}, {"v": float("inf")}, {"v": 3.0}, {"v": float("nan")}]
    column = profile_rows(rows)["columns"]["v"]
    assert (column["min"], column["max"], column["mean"]) == (1.0, 3.0, 2.0)
    assert column["non_finite"] == 2
    assert infer_schema(rows)["v"]["min"] == 1.0


def test_an_unknown_verify_mode_is_refused_and_case_is_ignored():
    from je_auto_control.utils.verify_field.verify_field import compare_field_value
    assert compare_field_value("Hello", "hello", mode="CI")["match"] is True
    with pytest.raises(ValueError):
        compare_field_value("x", "x", mode="bogus")


def test_accent_position_and_decomposed_input_collate():
    from je_auto_control.utils.locale_collation.locale_collation import compare, sort_strings
    assert compare("éa", "eá") != 0
    assert compare("éa", "eá", strength="secondary") != 0
    assert compare("éa", "eá", strength="primary") == 0
    assert compare("e", "é") == -1 and compare("resume", "résumé") == -1
    swedish = "abcdefghijklmnopqrstuvwxyzåäö"
    decomposed = "a" + chr(0x30A)
    assert sort_strings([decomposed, "z", "b"], tailoring=swedish) == ["b", "z", decomposed]


def _cf_html(fragment):
    body = f"<html><body>{fragment}</body></html>"
    header = ("Version:0.9\r\nStartHTML:{0:010d}\r\nEndHTML:{1:010d}\r\n"
              "StartFragment:{2:010d}\r\nEndFragment:{3:010d}\r\n")
    size = len(header.format(0, 0, 0, 0).encode("utf-8"))
    start = size + len(b"<html><body>")
    end = start + len(fragment.encode("utf-8"))
    return header.format(size, size + len(body.encode("utf-8")), start, end) + body


def test_a_str_payload_without_markers_uses_the_offsets():
    from je_auto_control.utils.rich_clipboard.rich_clipboard import parse_cf_html
    payload = _cf_html("<b>café</b>")
    assert parse_cf_html(payload.encode("utf-8")) == "<b>café</b>"
    assert parse_cf_html(payload) == "<b>café</b>"


def test_a_non_ascii_digit_is_not_a_role_number():
    from je_auto_control.utils.ax_tree_walk.ax_tree_walk import (
        AXTreeNode, find_by_path, humanize_role,
    )
    assert humanize_role("ControlType_²") == "ControlType_²"
    assert find_by_path(AXTreeNode(name="root", role="Pane", bounds=(0, 0, 1, 1)),
                        "0.²") is None


def test_hsv_bounds_outside_uint8_are_clamped_or_wrapped():
    from je_auto_control.utils.hsv_segment.hsv_segment import (
        dominant_hue_regions, segment_hsv,
    )
    image = np.zeros((40, 60, 3), np.uint8)
    image[:, :20] = (255, 0, 0)          # hue 0
    image[:, 40:] = (0, 0, 255)          # hue 120
    everything = segment_hsv(image, lower_hsv=[-1, 1, 1], upper_hsv=[180, 256, 256])
    assert len(everything) == 2
    assert len(dominant_hue_regions(image, hue=170, hue_tol=200)) == 2   # the whole circle
    assert [box["x"] for box in dominant_hue_regions(image, hue=-5, hue_tol=6)] == [0]
    assert [box["x"] for box in dominant_hue_regions(image, hue=300, hue_tol=5)] == [40]
    with pytest.raises(ValueError):
        dominant_hue_regions(image, hue=0, hue_tol=-1)
