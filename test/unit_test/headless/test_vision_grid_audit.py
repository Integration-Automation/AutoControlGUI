"""Perceptual diff, text regions, rotated matches, actionability, the project template, grid fill.

An empty image aborted the executor; a one-pixel change passed a zero budget;
text regions answered region-local boxes; match_rotated_all found one copy per
pose; a falsy enabled probe, NumPy tokens and a zero stability wait misjudged
readiness; the generated project's example failed validation; a spanning box
was counted twice, and Tesseract's box shape raised KeyError.
"""
import numpy as np
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException


def test_an_empty_image_is_a_framework_error_and_one_pixel_breaks_a_zero_budget(tmp_path):
    from je_auto_control.utils.executor.action_executor import execute_action
    from je_auto_control.utils.perceptual_diff.perceptual_diff import assert_perceptual, perceptual_diff
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    with pytest.raises(AutoControlException):
        perceptual_diff(str(empty), str(empty))
    assert "failed" in str(execute_action([["AC_perceptual_diff", {"actual": str(empty), "expected": str(empty)}]]))
    frame = np.zeros((1080, 1920, 3), np.uint8)
    changed = frame.copy()
    changed[500, 900] = 255
    with pytest.raises(AutoControlException, match="1 pixels changed"):
        assert_perceptual(changed, frame)


def test_text_regions_answer_in_screen_coordinates(monkeypatch):
    import cv2
    from je_auto_control.utils.text_regions.text_regions import find_text_lines, find_text_regions
    from je_auto_control.utils.visual_match import visual_match
    image = np.full((120, 300), 235, np.uint8)
    for index, char in enumerate("ABCD"):
        cv2.putText(image, char, (20 + index * 30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    monkeypatch.setattr(visual_match, "_grab_gray_with_origin", lambda region: (image, 500, 300))
    assert min(box["x"] for box in find_text_regions(region=[500, 300, 300, 120])) >= 500
    assert find_text_lines(region=[500, 300, 300, 120])[0]["y"] >= 300


def test_every_copy_of_a_rotated_template_is_found():
    from je_auto_control.utils.rotated_match.rotated_match import match_rotated_all
    rng = np.random.default_rng(3)
    template = rng.integers(0, 255, (20, 20), dtype=np.uint8)
    haystack = np.zeros((100, 200), np.uint8)
    for x in (10, 80, 150):
        haystack[30:50, x:x + 20] = template
    assert sorted(match.x for match in match_rotated_all(template, haystack=haystack, min_score=0.9)) == [10, 80, 150]


def _config(timeout_s=1.0, stable_for_s=0.2):
    from je_auto_control.utils.actionability import GateConfig
    now = [0.0]
    return GateConfig(timeout_s=timeout_s, stable_for_s=stable_for_s, poll_interval_s=0.1,
                      clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))


@pytest.mark.parametrize("probe", [lambda: np.False_, lambda: 0])
def test_a_falsy_enabled_probe_means_disabled(probe):
    from je_auto_control.utils.actionability import wait_actionable
    report = wait_actionable(lambda: (0, 0, 10, 10), enabled_probe=probe, config=_config())
    assert (report.actionable, report.reason) == (False, "disabled")


def test_numpy_tokens_and_a_zero_wait_are_handled():
    from je_auto_control.utils.actionability import wait_actionable
    frame = np.zeros((40, 40), np.uint8)
    report = wait_actionable(lambda: np.array([10, 10, 20, 20]),
                             region_sampler=lambda box: frame[10:30, 10:30].copy(), config=_config())
    assert report.actionable
    assert wait_actionable(lambda: (0, 0, 10, 10), config=_config(timeout_s=0, stable_for_s=0)).actionable


def test_the_generated_project_example_validates(tmp_path):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.executor.action_schema import validate_actions
    from je_auto_control.utils.json.json_file import read_action_json
    from je_auto_control.utils.project.create_project_structure import create_project_dir
    create_project_dir(str(tmp_path), "Demo")
    [keyword] = list(tmp_path.rglob("keyword1.json"))
    validate_actions(read_action_json(str(keyword)), executor.known_commands())


_GRID = {"cols": [0, 100, 200], "rows": [0, 30, 60]}


def test_a_spanning_box_is_counted_once_at_its_anchor():
    from je_auto_control.utils.table_grid_fill import populate_table
    result = populate_table(_GRID, [{"x": 10, "y": 5, "width": 180, "height": 20, "text": "Merged Header"}])
    assert [cell["text"] for cell in result["cells"] if cell["text"]] == ["Merged Header"]
    assert {"row": 0, "col": 0, "text": "Merged Header"} in result["cells"]
    assert result["spans"][0]["col_span"] == 2
    sliver = populate_table(_GRID, [{"x": 20, "y": 5, "width": 85, "height": 20, "text": "Wide"}])
    assert sliver["spans"] == [] and {"row": 0, "col": 0, "text": "Wide"} in sliver["cells"]


def test_tesseract_boxes_are_read_and_bad_boxes_are_value_errors():
    from je_auto_control.utils.table_grid_fill import assign_text_to_grid
    tesseract_box = {"left": 10, "top": 5, "width": 60, "height": 20, "text": "Name"}
    assert assign_text_to_grid(_GRID, [tesseract_box])[0][0] == "Name"
    with pytest.raises(ValueError):
        assign_text_to_grid(_GRID, [{"x": 10, "width": 60, "height": 20}])
