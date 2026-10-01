"""Grid boxes in both layouts, macOS field clearing, dataset keys and cells, co-failures, critic effects, TOTP time.

``AC_locate_all_image`` boxes are ``[left, top, right, bottom]`` but the grid
read every box as ``[x, y, w, h]``; the field clear step pressed a key macOS
does not have; a misspelt dataset key compared two arbitrary rows; a new
``None`` column and NaN cells disagreed between the diff and its cells; a run
given as one name split into letters; an unknown effect scored as a success;
NaN or huge TOTP times escaped the exception family and a negative window
rejected every code; a merged config shared the defaults' sub-dicts.
"""
import sys

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException

_CELLS = [[100, 200, 40, 20], [200, 200, 40, 20], [100, 300, 40, 20], [200, 300, 40, 20]]


def test_grid_cells_from_ltrb_boxes_dicts_and_matches():
    from je_auto_control.utils.grid_locator import locate_cell
    ltrb = [[x, y, x + w, y + h] for x, y, w, h in _CELLS]
    assert locate_cell(ltrb, 1, 1, box_format="ltrb")["center"] == [220, 310]
    assert locate_cell(_CELLS, 1, 1)["center"] == [220, 310]
    dicts = [{"x": x, "y": y, "width": w, "height": h} for x, y, w, h in _CELLS]
    assert locate_cell(dicts, 0, 1)["center"] == [220, 210]
    with pytest.raises(ValueError):
        locate_cell(_CELLS, 0, 0, box_format="xyxy")


def test_the_grid_command_takes_the_box_format():
    from je_auto_control.utils.executor.action_executor import Executor
    ltrb = [[x, y, x + w, y + h] for x, y, w, h in _CELLS]
    record = Executor().execute_action([["AC_grid_cell", {"boxes": ltrb, "row": 1, "col": 1, "box_format": "ltrb"}]])
    assert list(record.values())[0]["center"] == [220, 310]


@pytest.mark.parametrize("platform, key", [("darwin", "backspace"), ("win32", "delete"), ("linux", "delete")])
def test_the_field_is_cleared_with_a_key_the_platform_has(platform, key, monkeypatch):
    from je_auto_control.utils.field_entry.field_entry import plan_field_set
    monkeypatch.setattr(sys, "platform", platform)
    plan = plan_field_set("hi", modifier="command" if platform == "darwin" else "ctrl")
    assert {"op": "key", "key": key} in plan


def test_a_missing_dataset_key_is_refused_and_cells_agree_with_rows():
    from je_auto_control.utils.dataset_diff import cell_changes, diff_rows
    old = [{"id": 1, "v": 1}, {"id": 2, "v": 2}]
    new = [{"id": 1, "v": 1}, {"id": 3, "v": 3}]
    with pytest.raises(ValueError, match="'ID'"):
        diff_rows(old, new, "ID")
    with pytest.raises(ValueError):
        diff_rows(old, new, [])
    assert cell_changes([{"id": 1}], [{"id": 1, "note": None}], "id") == [
        {"key": 1, "column": "note", "old": None, "new": None}]
    nan = float("nan")
    assert diff_rows([{"id": 1, "v": nan}], [{"id": 1, "v": float("nan")}], "id")["changed"] == []
    assert cell_changes([{"id": 1, "v": nan, "w": 1}], [{"id": 1, "v": float("nan"), "w": 2}], "id") == [
        {"key": 1, "column": "w", "old": 1, "new": 2}]


def test_a_run_given_as_one_name_and_pairs_that_never_failed_together():
    from je_auto_control.utils.flake_cluster import cofailure_pairs, failure_clusters
    clusters = failure_clusters([["test_login", "test_logout"], "test_login", ["test_login", "test_logout"]],
                                min_size=1)
    assert sorted(test for cluster in clusters for test in cluster["tests"]) == ["test_login", "test_logout"]
    assert cofailure_pairs([["a"], ["b"]], threshold=0) == []
    assert failure_clusters([["a"], ["b"]], threshold=0) == []


@pytest.mark.parametrize("effect", ["error", "noop"])
def test_an_unknown_effect_is_refused(effect):
    from je_auto_control.utils.critic_features import score_step_rule_based
    with pytest.raises(ValueError, match="unknown effect"):
        score_step_rule_based({"effect": {"effect": effect}})
    assert score_step_rule_based({"effect": {"effect": "no_op"}})["outcome"] is False


_SECRET = "JBSWY3DPEHPK3PXP"


@pytest.mark.parametrize("at", [float("nan"), float("inf"), 1e21, -1.0])
def test_totp_times_outside_the_range_are_framework_errors(at):
    from je_auto_control.utils.otp import generate_totp, verify_totp
    with pytest.raises(AutoControlException):
        generate_totp(_SECRET, at=at)
    with pytest.raises(AutoControlException):
        verify_totp(_SECRET, "123456", at=at)


def test_a_negative_totp_window_is_refused_and_zero_accepts_the_current_code():
    from je_auto_control.utils.otp import generate_totp, verify_totp
    code = generate_totp(_SECRET, at=1_000_000.0)
    assert verify_totp(_SECRET, code, at=1_000_000.0, window=0)
    with pytest.raises(AutoControlException):
        verify_totp(_SECRET, code, at=1_000_000.0, window=-1)


def test_a_merged_config_shares_nothing_with_its_defaults():
    from je_auto_control.utils.layered_config import deep_merge
    defaults = {"db": {"host": "localhost", "port": 5432}, "debug": False}
    merged = deep_merge(defaults, {"debug": True})
    merged["db"]["host"] = "prod"
    assert defaults["db"]["host"] == "localhost"


def test_a_line_without_text_adds_no_word():
    from je_auto_control.utils.text_blocks import group_paragraphs
    lines = [{"text": "Hello", "left": 0, "top": 0, "width": 50, "height": 10},
             {"text": None, "left": 0, "top": 12, "width": 50, "height": 10}]
    assert [paragraph["text"] for paragraph in group_paragraphs(lines)] == ["Hello"]
