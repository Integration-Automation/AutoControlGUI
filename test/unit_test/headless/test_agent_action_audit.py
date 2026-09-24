"""Agent / action defects from the 2026-09-24 audit (fakes only).

Self-healing replay "healed" a failed assertion and reported success, and
left a healed press's release at the old spot; list-form actions crashed
relocation; zero-size boxes and unknown enabled-state counted as actionable /
disabled; act_in_view gated on a constant box; grounding snapped to the
outermost element and let -0.9 pass the bounds check; one non-string memory
tag broke every recall; a losing key-file creator read an empty key; prune
removed a run still in progress.
"""
import threading
import time

import pytest

from je_auto_control.utils.act_in_view.act_in_view import ScrollPlan, act_in_view
from je_auto_control.utils.action_grounding.action_grounding import in_bounds, snap_to_element
from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
from je_auto_control.utils.actionability.actionability import GateConfig, wait_actionable
from je_auto_control.utils.agent_memory.agent_memory import AgentMemory
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAssertionException,
)
from je_auto_control.utils.run_history.history_store import HistoryStore
from je_auto_control.utils.semantic_recording.replay import relocate_recording
from je_auto_control.utils.semantic_recording.self_healing import SelfHealingReplayer

ANCHOR = {"role": "button", "name": "OK"}


def test_a_failed_assertion_is_not_healed():
    def execute(action):
        raise AutoControlAssertionException("text never appeared")

    replayer = SelfHealingReplayer(execute, vlm_locate=lambda _d: (500, 500))
    with pytest.raises(AutoControlAssertionException):
        replayer.replay([{"action": "mouse_press", "x": 1, "y": 1, "anchor": ANCHOR}])


def test_the_release_follows_its_healed_press():
    calls = []

    def execute(action):
        calls.append((action["action"], action["x"], action["y"]))
        if action["action"] == "mouse_press" and not action.get("healed"):
            raise AutoControlActionException("not there")

    replayer = SelfHealingReplayer(execute, vlm_locate=lambda _d: (500, 500))
    result = replayer.replay([
        {"action": "mouse_press", "x": 1, "y": 1, "anchor": ANCHOR},
        {"action": "mouse_release", "x": 1, "y": 1, "anchor": ANCHOR},
    ])
    assert result.succeeded
    assert calls[-1] == ("mouse_release", 500, 500)


def test_list_form_actions_pass_through_relocation():
    entry = ["AC_click_mouse", {"x": 1}]
    assert relocate_recording([entry], locator=object()) == [entry]


def _gate(**kwargs):
    ticks = iter(range(1000))
    config = GateConfig(timeout_s=0.5, stable_for_s=0.0, poll_interval_s=0.1,
                        clock=lambda: next(ticks) * 0.1, sleep=lambda _s: None)
    return wait_actionable(config=config, **kwargs)


def test_a_zero_size_box_is_not_visible():
    report = _gate(bbox_provider=lambda: (-500, -500, 0, 0))
    assert not report.actionable and not report.visible


def test_an_unknown_enabled_state_is_not_disabled():
    report = _gate(bbox_provider=lambda: (0, 0, 10, 10), enabled_probe=lambda: None)
    assert report.actionable


def test_act_in_view_gates_on_the_live_target():
    positions = iter([(5, 5), None, None, None, None, None, None, None, None, None])
    plan = ScrollPlan(locator=lambda _t: next(positions, None), scroller=lambda *_a: None)
    ticks = iter(range(1000))
    config = GateConfig(timeout_s=0.5, stable_for_s=0.0, poll_interval_s=0.1,
                        clock=lambda: next(ticks) * 0.1, sleep=lambda _s: None)
    with pytest.raises(AutoControlActionException):
        act_in_view("t", lambda point: point, scroll=plan, config=config)


def test_grounding_snaps_to_the_innermost_element_and_bounds_are_exact():
    window = {"x": 0, "y": 0, "width": 1000, "height": 800}
    button = {"x": 10, "y": 10, "width": 20, "height": 20}
    assert snap_to_element(15, 15, [window, button]) == [20, 20]
    assert in_bounds(-0.9, -0.9, (100, 100)) is False
    assert in_bounds(99.5, 0, (100, 100)) is True


def test_a_non_string_tag_does_not_break_recall(tmp_path):
    memory = AgentMemory(str(tmp_path / "m.db"))
    memory.remember("other", tags=[1, None])
    memory.remember("log in", tags=["login"])
    assert [episode.goal for episode in memory.recall("login")][:1] == ["log in"]


def test_a_losing_key_creator_waits_for_the_key(tmp_path):
    path = tmp_path / "k.key"
    path.write_bytes(b"")

    def finish_writing():
        time.sleep(0.1)
        path.write_bytes(b"k" * 32)

    writer = threading.Thread(target=finish_writing)
    writer.start()
    try:
        assert load_or_create_key_file(path, lambda: b"x" * 32, 32) == b"k" * 32
    finally:
        writer.join()


def test_prune_keeps_a_run_still_in_progress(tmp_path):
    store = HistoryStore(str(tmp_path / "h.db"))
    live = store.start_run("scheduler", "live", "p", started_at=time.time())
    for index in range(3):
        run = store.start_run("scheduler", f"done{index}", "p", started_at=time.time() - 10 + index)
        store.finish_run(run, "ok")
    store.prune(keep_latest=0)
    assert store.finish_run(live, "ok") is True
