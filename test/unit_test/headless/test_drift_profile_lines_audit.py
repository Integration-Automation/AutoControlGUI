"""Drift with NaN, profiles of mixed / huge / bool columns, short lines, 16-bit annotations, test selection, run diffs.

NaN moved the KS statistic by position alone; a mixed column's inferred schema
rejected its own rows, and huge values or a column with no finite value
crashed the profile or the validator; ``True`` and ``1`` counted as one value; lines shorter than
50 px were never found and 16-bit images raised ``cv2.error``; 16-bit and
float screenshots annotated as black and white; runs killed mid-flight hid a
flow's history; a step going from 0 s to 30 s was not a regression; negative
n-gram lengths counted the empty sequence; an empty baggage key formatted as
a member no parser reads.
"""
import cv2
import numpy as np
import pytest
from PIL import Image

from je_auto_control.utils.exception.exceptions import AutoControlException


# --- drift ----------------------------------------------------------------------

@pytest.mark.parametrize("name", ["ks", "psi"])
def test_nan_in_a_drift_sample_is_refused(name):
    from je_auto_control.utils.data_drift import ks_two_sample, psi
    test = ks_two_sample if name == "ks" else psi
    reference = [float(index) for index in range(100)]
    with pytest.raises(ValueError, match=r"current\[50\] is NaN"):
        test(reference, reference[:50] + [float("nan")] + reference[50:])
    with pytest.raises(ValueError, match=r"reference\[0\] is NaN"):
        test([float("nan")] + reference, reference)


# --- profiles and the schemas inferred from them ----------------------------------------------------------------------

@pytest.mark.parametrize("rows", [
    [{"v": 30}, {"v": "unknown"}, {"v": 41}],
    [{"v": float("inf")}, {"v": float("nan")}],
    [{"v": True}, {"v": 1}, {"v": 2}],
    [{"v": 10 ** 400}, {"v": 1}],
    [{"v": 2 ** 60 + 1}, {"v": 2 ** 60 + 3}],
])
def test_an_inferred_schema_accepts_the_rows_it_came_from(rows):
    from je_auto_control.utils.data_profile import infer_schema
    from je_auto_control.utils.data_quality.data_quality import validate_rows
    report = validate_rows(rows, infer_schema(rows))
    assert report["ok"], report["errors"]


def test_profiles_survive_huge_values_and_keep_bools_apart():
    from je_auto_control.utils.data_profile import profile_rows
    huge = profile_rows([{"v": 1e308}, {"v": 1e308}])["columns"]["v"]
    assert huge["mean"] == 1e308
    exact = profile_rows([{"v": 10 ** 400}, {"v": 2 ** 60 + 1}])["columns"]["v"]
    assert (exact["min"], exact["max"], exact["mean"]) == (2 ** 60 + 1, 10 ** 400, None)
    column = profile_rows([{"v": True}, {"v": 1}, {"v": 2}])["columns"]["v"]
    assert column["distinct"] == 3 and column["inferred_type"] == "mixed"
    assert {entry["value"] for entry in column["top_values"]} == {True, 1, 2}


def test_true_and_one_are_not_duplicates_but_one_and_one_are():
    from je_auto_control.utils.data_quality.data_quality import validate_rows
    assert validate_rows([{"f": True}, {"f": 1}], {"f": {"unique": True}})["ok"]
    assert not validate_rows([{"f": 1}, {"f": 1}], {"f": {"unique": True}})["ok"]


# --- lines ----------------------------------------------------------------------

def _divider(length, dtype=np.uint8, ink=0):
    image = np.full((120, 200), 255, np.uint8)
    cv2.line(image, (20, 60), (20 + length, 60), ink, 2)
    return image.astype(dtype) * (257 if dtype == np.uint16 else 1)


@pytest.mark.parametrize("length", [30, 40])
def test_a_line_shorter_than_fifty_pixels_is_found(length):
    from je_auto_control.utils.edge_lines import find_lines, find_separators
    assert find_lines(_divider(length), min_length=20)
    assert find_separators(_divider(length), min_length=20) in ([59], [60], [61])


def test_sixteen_bit_images_are_read_and_opencv_errors_are_framework_errors(monkeypatch):
    from je_auto_control.utils.edge_lines import find_lines
    assert find_lines(_divider(100, np.uint16), min_length=20)

    def broken(*_args, **_kwargs):
        raise cv2.error("degenerate input")

    monkeypatch.setattr(cv2, "HoughLinesP", broken)
    with pytest.raises(AutoControlException):
        find_lines(_divider(100), min_length=20)


# --- annotations ----------------------------------------------------------------------

@pytest.mark.parametrize("image", [
    Image.fromarray(np.tile(np.linspace(0, 65535, 64).astype(np.uint16), (8, 1))),
    Image.fromarray(np.tile(np.linspace(0, 1, 64, dtype=np.float32), (8, 1))),
])
def test_sixteen_bit_and_float_screenshots_keep_their_tones(image, tmp_path):
    from je_auto_control.utils.annotate import annotate_screenshot
    out = annotate_screenshot(image, [], str(tmp_path / "out.png"))
    with Image.open(out) as result:
        assert len(np.unique(np.asarray(result.convert("L")))) > 32


# --- test selection ----------------------------------------------------------------------

def test_runs_killed_mid_flight_do_not_hide_a_flows_history(tmp_path):
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.test_select import rank_flows, select_flows
    path = str(tmp_path / "history.sqlite")
    store = HistoryStore(path)
    for index in range(10):
        run = store.start_run("scheduler", "s", "A.json", started_at=1000.0 + index)
        store.finish_run(run, "error", finished_at=1001.0 + index)
    for index in range(30):
        store.start_run("scheduler", "s", "A.json", started_at=2000.0 + index)
    assert [run.status for run in store.list_runs(script_path="A.json", statuses=["error"])] == ["error"] * 10
    assert store.list_runs(statuses=[]) == []
    store.close()
    [ranked] = rank_flows(["A.json"], history_path=path, window=10.0)
    assert (ranked["runs"], ranked["failures"]) == (10, 10)
    assert select_flows(["A.json", "A.json"], history_path=path) == ["A.json"]
    with pytest.raises(ValueError):
        rank_flows(["A.json"], history_path=path, window=0)


def test_sharding_and_flakiness_read_finished_runs_past_killed_ones(tmp_path):
    from je_auto_control.utils.flakiness import analyze_flakiness
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.test_shard.test_shard import _durations
    path = str(tmp_path / "history.sqlite")
    store = HistoryStore(path)
    for index in range(10):
        run = store.start_run("scheduler", "s", "A.json", started_at=1000.0 + 10 * index)
        store.finish_run(run, "error" if index % 2 else "ok", finished_at=1005.0 + 10 * index)
    for index in range(30):
        store.start_run("scheduler", "s", "A.json", started_at=2000.0 + index)
    [entry] = analyze_flakiness(store, limit=10).entries
    assert (entry.total_runs, entry.flaky) == (10, True)
    store.close()
    assert _durations(["A.json"], path, 10) == {"A.json": 5.0}


# --- run diffs, mining, baggage ----------------------------------------------------------------------

def test_a_step_that_took_no_time_can_regress_and_infinite_durations_are_not_compared():
    from je_auto_control.utils.run_diff import diff_runs
    [regression] = diff_runs([{"name": "a", "duration": 0.0}],
                             [{"name": "a", "duration": 30.0}])["timing_regressions"]
    assert regression["ratio"] is None and regression["after"] == 30.0
    assert not diff_runs([{"name": "a", "duration": 0.0}], [{"name": "a", "duration": 0.05}])["timing_regressions"]
    assert not diff_runs([{"name": "a", "duration": 1.0}],
                         [{"name": "a", "duration": float("inf")}])["timing_regressions"]
    assert diff_runs([{"name": "a", "duration": 1.0}],
                     [{"name": "a", "duration": 2.0}])["timing_regressions"][0]["ratio"] == 2.0


@pytest.mark.parametrize("bounds", [{"min_len": 0, "max_len": 1}, {"min_len": -2, "max_len": -2},
                                    {"min_len": 3, "max_len": 2}, {"min_count": 0}])
def test_mining_refuses_empty_or_inverted_lengths(bounds):
    from je_auto_control.utils.process_mining import find_repeated_sequences, mine_action_log
    with pytest.raises(ValueError):
        find_repeated_sequences(["AC_a", "AC_b"], **bounds)
    with pytest.raises(ValueError):
        mine_action_log(["AC_a", "AC_b"], **bounds)


def test_an_empty_baggage_key_is_refused():
    from je_auto_control.utils.baggage import Baggage, format_baggage, parse_baggage
    with pytest.raises(ValueError):
        Baggage({"": "x"})
    with pytest.raises(ValueError):
        Baggage().set("", "x")
    header = format_baggage(Baggage({"user id": "a,b;c=d"}))
    assert parse_baggage(header).to_dict() == {"user id": "a,b;c=d"}
