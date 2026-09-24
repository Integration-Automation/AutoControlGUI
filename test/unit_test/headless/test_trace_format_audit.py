"""Trace, report and helper defects from the 2026-09-24 audit (pure; no desktop).

A replay trace holding U+2028 could not be read back; one frame matching
elsewhere still counted as persisted; ``hold_modifiers("shift")`` pressed five
letters; a misspelt annotation level became ``error``; a box off the frame's
left edge scored real pixels; OTLP output held ``NaN`` and Python reprs; the
SOP generator read a wrapped action file by its keys.
"""
import json

import numpy as np
import pytest


def test_a_trace_with_unicode_line_separators_round_trips():
    from je_auto_control.utils.agent_replay import agent_replay
    trace = []
    agent_replay.record_step(trace, "line1" + chr(0x2028) + "line2", ["AC_type_keyboard", {"text": "x"}])
    agent_replay.record_step(trace, "obs" + chr(0x85) + chr(0x2029), ["AC_x"])
    assert agent_replay.from_jsonl(agent_replay.to_jsonl(trace)) == trace
    assert agent_replay.from_jsonl('{"a": 1}\r\n{"a": 2}\r\n') == [{"a": 1}, {"a": 2}]


def test_one_frame_matching_elsewhere_is_not_persistence(monkeypatch):
    from je_auto_control.utils import visual_match
    from je_auto_control.utils.match_stability.match_stability import match_persistence

    class _Hit:
        def __init__(self, center):
            self.center = center

    centers = iter([[100, 100]] * 9 + [[400, 300]])
    monkeypatch.setattr(visual_match, "match_template",
                        lambda *_args, **_kwargs: _Hit(next(centers)))
    assert match_persistence("t", list(range(10)))["persisted"] is False
    steady = iter([[100, 100]] * 10)
    monkeypatch.setattr(visual_match, "match_template",
                        lambda *_args, **_kwargs: _Hit(next(steady)))
    assert match_persistence("t", list(range(10)))["persisted"] is True


def test_one_modifier_name_is_one_key():
    from je_auto_control.utils.modifier_state.modifier_state import (
        hold_modifiers, plan_with_modifiers,
    )
    events = []
    with hold_modifiers("shift", sink=events.append):
        pass
    assert events == [{"op": "press", "key": "shift"}, {"op": "release", "key": "shift"}]
    assert [step["key"] for step in plan_with_modifiers([], "ctrl")] == ["ctrl", "ctrl"]


def test_an_unknown_annotation_level_is_refused():
    from je_auto_control.utils.ci_annotations.ci_annotations import format_annotation
    with pytest.raises(ValueError):
        format_annotation({"level": "warn", "message": "x"})
    assert format_annotation({"message": None}) == "::error::"
    assert format_annotation({"level": "WARNING", "message": "m"}) == "::warning::m"


def test_a_box_off_the_frame_scores_nothing():
    from je_auto_control.utils.change_localize.change_localize import localize_changes
    reference = np.zeros((100, 100), np.uint8)
    current = reference.copy()
    current[:, :50] = 255
    for box in ([-60, 0, 20, 100], [0, -60, 20, 20]):
        (entry,) = localize_changes(reference, [box], current=current)
        assert entry["score"] == 0.0 and entry["changed"] is False, box
    (partly,) = localize_changes(reference, [[-10, 0, 20, 100]], current=current)
    assert partly["score"] == 1.0


def test_otlp_output_is_strict_json_with_typed_values(tmp_path):
    from je_auto_control.utils.otlp_export.otlp_export import spans_to_otlp, write_otlp
    payload = spans_to_otlp([{
        "trace_id": "ab" * 16, "span_id": "cd" * 8, "name": "step",
        "start_unix_nano": 1.7e18, "end_unix_nano": 1700000000000000001,
        "attributes": {"score": float("nan"), "peak": float("-inf"),
                       "tags": ["x", 2], "meta": {"k": True}},
    }])
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["startTimeUnixNano"] == "1700000000000000000"
    assert span["endTimeUnixNano"] == "1700000000000000001"
    values = {item["key"]: item["value"] for item in span["attributes"]}
    assert values["score"] == {"doubleValue": "NaN"}
    assert values["peak"] == {"doubleValue": "-Infinity"}
    assert values["tags"] == {"arrayValue": {"values": [{"stringValue": "x"}, {"intValue": "2"}]}}
    assert values["meta"] == {"kvlistValue": {"values": [{"key": "k", "value": {"boolValue": True}}]}}

    def refuse(token):
        raise AssertionError(f"non-JSON token {token}")

    path = write_otlp(payload, str(tmp_path / "trace.json"))
    with open(path, encoding="utf-8") as handle:
        json.loads(handle.read(), parse_constant=refuse)


def test_the_sop_reads_every_action_file_shape():
    from je_auto_control.utils.process_doc.process_doc import generate_sop
    wrapped = generate_sop({"auto_control": [["AC_write", {"write_string": "hi"}]]})
    assert [step["command"] for step in wrapped["steps"]] == ["AC_write"]
    assert generate_sop(["AC_screenshot"])["steps"][0]["command"] == "AC_screenshot"
    with pytest.raises(ValueError):
        generate_sop([None])
