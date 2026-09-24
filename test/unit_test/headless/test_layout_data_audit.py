"""Layout / data-check / locale defects from the 2026-09-24 audit.

Flow selection and sharding read one global newest-N window, so a flow whose
runs were older than N unrelated runs looked untested; XY-cut spent its
depth budget on stacked paragraphs and then interleaved columns; config
fields ignored ``env`` and truncated 2.9 to 2; dbt-style uniqueness counted
nulls; unit lists dropped the conjunction CLDR uses outside English; the A2A
card's modes were not MIME types; ``within`` kept a centre one pixel outside
the region; UIA read the Value / RangeValue state behind the wrong pattern ids.
"""
from je_auto_control.utils.a2a.agent_card import build_agent_card
from je_auto_control.utils.accessibility.backends.windows_state import read_state
from je_auto_control.utils.config_schema.config_schema import validate_config
from je_auto_control.utils.list_format.list_format import format_list
from je_auto_control.utils.locator_chain.locator_chain import from_boxes
from je_auto_control.utils.reading_flow.reading_flow import flow_order
from je_auto_control.utils.referential.referential import check_unique_key
from je_auto_control.utils.run_history.history_store import HistoryStore
from je_auto_control.utils.test_select.test_select import rank_flows
from je_auto_control.utils.test_shard.test_shard import _durations


def _history(tmp_path, flow_status):
    path = str(tmp_path / "history.db")
    store = HistoryStore(path)
    now = 1_000_000.0
    for index in range(10):
        run = store.start_run("scheduler", "s", "A.json", started_at=now + index)
        store.finish_run(run, flow_status, finished_at=now + index + 5)
    for index in range(150):
        run = store.start_run("scheduler", "s", "other.json", started_at=now + 100 + index)
        store.finish_run(run, "ok", finished_at=now + 101 + index)
    store.close()
    return path


def test_a_flow_behind_many_unrelated_runs_still_has_history(tmp_path):
    path = _history(tmp_path, "error")
    ranked = {row["flow"]: row for row in rank_flows(["A.json", "B.json"], history_path=path)}
    assert ranked["A.json"]["runs"] == 10
    assert ranked["A.json"]["last_status"] == "error"
    assert ranked["B.json"]["runs"] == 0
    assert _durations(["A.json"], path, 20) == {"A.json": 5.0}


def test_list_runs_filters_by_script_before_the_limit(tmp_path):
    store = HistoryStore(_history(tmp_path, "ok"))
    try:
        runs = store.list_runs(limit=3, script_path="A.json")
        assert [run.script_path for run in runs] == ["A.json"] * 3
        assert len(store.list_runs(limit=500, source_type="scheduler")) == 160
    finally:
        store.close()


def _box(text, x, y, width, height=20):
    return {"text": text, "x": x, "y": y, "width": width, "height": height}


def test_columns_below_many_paragraphs_are_read_down_each_column():
    boxes = [_box(f"P{i}", 0, i * 40, 400) for i in range(9)]
    for row in range(3):
        boxes += [_box(f"A{row}", 0, 360 + row * 40, 180), _box(f"B{row}", 220, 360 + row * 40, 180)]
    order = [box["text"] for box in flow_order(boxes)]
    assert order[9:] == ["A0", "A1", "A2", "B0", "B1", "B2"]


def test_config_reads_env_and_refuses_a_lossy_int():
    spec = {"port": {"type": "int", "required": True, "env": "AC_PORT"}}
    assert validate_config(spec, {}, environ={"AC_PORT": "8080"})["config"] == {"port": 8080}
    assert validate_config(spec, {"port": 1}, environ={"AC_PORT": "8080"})["config"] == {"port": 1}
    assert not validate_config(spec, {}, environ={})["ok"]
    assert not validate_config({"r": {"type": "int"}}, {"r": 2.9})["ok"]
    assert validate_config({"r": {"type": "int"}}, {"r": 3.0})["config"] == {"r": 3}


def test_unique_key_skips_nulls_on_one_column_only():
    assert check_unique_key([{"id": None}, {"id": None}, {"id": 1}], "id")["ok"]
    composite = check_unique_key([{"a": None, "b": 1}, {"a": None, "b": 1}], ["a", "b"])
    assert not composite["ok"]


def test_unit_lists_follow_cldr():
    items = ["A", "B", "C"]
    assert format_list(items, style="unit", locale="en") == "A, B, C"
    assert format_list(items, style="unit", locale="fr") == "A, B et C"
    assert format_list(items, style="unit", locale="es") == "A, B y C"
    assert format_list(items, style="unit", locale="pt") == "A, B e C"
    assert format_list(items, style="unit", locale="de") == "A, B und C"
    assert format_list(["A", "B"], style="unit", locale="de") == "A, B"
    assert format_list(["A", "B"], style="unit", locale="fr") == "A et B"


def test_agent_card_modes_are_media_types():
    card = build_agent_card()
    assert card["defaultInputModes"] == ["text/plain"]
    assert card["defaultOutputModes"] == ["text/plain"]


def test_within_excludes_the_pixel_past_the_region():
    boxes = [_box("edge", 5, 5, 10, 10), _box("inside", 0, 0, 10, 10)]
    kept = from_boxes(boxes).within([0, 0, 10, 10]).resolve()
    assert [box["text"] for box in kept] == ["inside"]


class _Element:
    """A UIA element that is an edit with a value and a slider range."""

    PROPS = {30019: False, 30043: True, 30045: "hello", 30046: False,
             30033: True, 30047: 42.0, 30029: False, 30034: False}

    def GetCurrentPropertyValue(self, property_id):  # noqa: N802 - COM name
        return self.PROPS.get(property_id)


def test_uia_state_uses_the_value_and_range_value_pattern_ids():
    state = read_state(_Element())
    assert state["value"] == "hello"
    assert state["number"] == 42.0
