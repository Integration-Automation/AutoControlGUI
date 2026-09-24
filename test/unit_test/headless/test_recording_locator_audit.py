"""Scripting, recording and locator helpers at the edges the audit found.

Dotted trigger variables (``${webhook.body}``), repair verdicts given as an
``EffectVerdict`` or a dict, a heal log with a torn multi-byte line, A/B
stats written by another store, an action logged before the first frame,
CJK recall, BOM-prefixed variable files and a fresh trace id per reset.
"""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.ab_locator.store import ABStore
from je_auto_control.utils.action_effect.action_effect import EffectVerdict
from je_auto_control.utils.agent_memory.agent_memory import AgentMemory
from je_auto_control.utils.agent_trace.agent_trace import AgentTrace
from je_auto_control.utils.script_vars.interpolate import interpolate_value, load_vars_from_json
from je_auto_control.utils.self_healing.heal_log import HealEvent, HealEventLog
from je_auto_control.utils.step_repair.step_repair import run_with_repair
from je_auto_control.utils.time_travel import ActionEvent, TimelinePlayer, save_action_log


def test_dotted_trigger_variables_resolve():
    variables = {"webhook.body": "payload", "webhook.query": {"ref": "main"},
                 "email.subject": "Hi", "user": {"name": "Ann"}}
    assert interpolate_value("${webhook.body}", variables) == "payload"
    assert interpolate_value("${webhook.query.ref}", variables) == "main"
    assert interpolate_value("${email.subject}", variables) == "Hi"
    assert interpolate_value("${user.name}", variables) == "Ann"
    with pytest.raises(ValueError, match="Unknown variable"):
        interpolate_value("${webhook.missing}", variables)


def test_the_trigger_variables_reach_a_script():
    from je_auto_control.utils.executor.action_executor import Executor
    executor = Executor()
    executor.variables.update_many({"webhook.body": "payload"})
    executor.execute_action([["AC_set_var", {"name": "copy", "value": "${webhook.body}"}]])
    assert executor.variables.get("copy") == "payload"


@pytest.mark.parametrize("verdict", [
    "no_op", {"effect": "no_op"},
    EffectVerdict(effect="no_op", changed_near_target=False, changed_count=0,
                  changed_centers=[], reason="nothing changed"),
])
def test_a_no_op_verdict_repeats_the_action_in_every_form(verdict):
    calls = []

    def act():
        calls.append(1)

    outcome = run_with_repair(act, lambda: len(calls) >= 2, verdict_for=lambda: verdict,
                              sleep=lambda _s: None)
    assert outcome.ok and len(calls) == 2


def test_a_torn_multibyte_line_skips_only_itself(tmp_path):
    log = HealEventLog(tmp_path / "heal.jsonl")
    event = HealEvent(timestamp="t", method="vlm", coordinates=[1, 2], duration_ms=1.0,
                      description="登入按鈕")
    log.append(event)
    torn = json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")
    with open(log.path, "ab") as handle:
        handle.write(torn[:torn.index("登".encode("utf-8")) + 1])
    log.append(event)
    assert len(log.list_events()) == 2


def test_ab_reports_see_another_stores_writes(tmp_path):
    path = tmp_path / "ab.json"
    reader, writer = ABStore(path), ABStore(path)
    assert reader.report("login").strategies == []
    writer.record(target_id="login", strategy="ocr", succeeded=True, elapsed_ms=5.0)
    assert [s.strategy for s in reader.report("login").strategies] == ["ocr"]
    assert [r.target_id for r in reader.all_reports()] == ["login"]


def test_a_strategy_that_never_won_is_not_recommended(tmp_path):
    store = ABStore(tmp_path / "ab.json")
    for _ in range(3):
        store.record(target_id="t", strategy="ocr", succeeded=False, elapsed_ms=1.0)
        store.record(target_id="t", strategy="image", succeeded=False, elapsed_ms=9.0)
    assert store.report("t").best_strategy() is None


def _write_manifest(directory: Path, frames: list) -> None:
    body = {"frame_count": len(frames), "entries": frames}
    (directory / "manifest.json").write_text(json.dumps(body), encoding="utf-8")
    for entry in frames:
        (directory / entry["filename"]).write_bytes(b"\xff\xd8\xff")


def test_an_action_before_the_first_frame_is_shown(tmp_path):
    _write_manifest(tmp_path, [{"filename": "a.jpg", "timestamp": 10.5, "size": 1},
                               {"filename": "b.jpg", "timestamp": 11.0, "size": 1}])
    save_action_log([ActionEvent(timestamp=10.0, action_name="AC_click_mouse"),
                     ActionEvent(timestamp=10.7, action_name="AC_write")],
                    tmp_path / "actions.jsonl")
    names = [a.action_name for a in TimelinePlayer(tmp_path).at_step(0).actions]
    assert names == ["AC_click_mouse", "AC_write"]


def test_recall_finds_a_cjk_keyword(tmp_path):
    memory = AgentMemory(str(tmp_path / "memory.db"))
    memory.remember("登入後台系統", outcome="ok")
    memory.remember("open the settings page", outcome="ok")
    hits = memory.recall("登入")
    assert [episode.goal for episode in hits] == ["登入後台系統"]
    assert [episode.goal for episode in memory.recall("settings")] == ["open the settings page"]


def test_a_bom_variables_file_loads(tmp_path):
    path = tmp_path / "vars.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"host": "example.org"}')
    assert load_vars_from_json(str(path)) == {"host": "example.org"}


def test_reset_starts_a_new_trace():
    trace = AgentTrace()
    first = trace._trace_id  # noqa: SLF001
    trace.reset()
    assert trace._trace_id != first  # noqa: SLF001
