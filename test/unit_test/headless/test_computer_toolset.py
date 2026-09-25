"""The GA computer toolset (``computer_toolset_20260801``) and three beta-path fixes.

Claude Opus 5.5 accepts computer use only as the toolset: each action is a
``tool_use`` named after the member, a turn may hold several, every
``tool_result`` carries ``toolset_name``, and screenshots must already fit the
image limits. The beta path also lost the drag end point (``coordinate``),
ignored ``key``'s ``repeat`` and a click's modifier ``text``. Stub client only.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends._computer_toolset import (
    MAX_LONG_EDGE_PX, MAX_VISUAL_TOKENS, fit_screenshot, visual_tokens,
)
from je_auto_control.utils.agent.backends.anthropic_computer_use import (
    ComputerUseAgentBackend, _decision_from_computer_action,
)
from je_auto_control.utils.agent.backends.base import AgentBackendError


@dataclass
class _Block:
    type: str
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    text: Optional[str] = None


class _Response:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, script):
        self.calls: List[Dict[str, Any]] = []
        self.script = list(script)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class _Client:
    """``messages`` only: the GA toolset must not go through the beta namespace."""

    def __init__(self, script):
        self.messages = _Messages(script)


def _png(width, height):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _step(index, tool, error=None):
    return AgentStep(index=index, tool=tool, arguments={}, result=None, error=error)


def _toolset_backend(script, width=3840, height=2160):
    client = _Client(script)
    backend = ComputerUseAgentBackend(display_width_px=width, display_height_px=height,
                                      client=client, model="claude-opus-5-5")
    return backend, client


def test_opus_5_5_gets_the_toolset_without_a_beta():
    batch = _Response([
        _Block("tool_use", id="t1", name="left_click", input={"coordinate": [100, 50]}),
        _Block("tool_use", id="t2", name="type", input={"text": "hi"}),
    ])
    done = _Response([_Block("text", text="done")], stop_reason="end_turn")
    backend, client = _toolset_backend([batch, done])
    screen = _png(3840, 2160)

    first = backend.decide_next_action("goal", screen, [])
    request = client.messages.calls[0]
    assert request["tools"] == [{"type": "computer_toolset_20260801"}]
    assert "betas" not in request and "tool_choice" not in request
    # 3840x2160 is fitted to 2576x1449 (4784 visual tokens), a scale of
    # about 0.671: model pixel (100, 50) is screen pixel (149, 75).
    assert first == {"tool": "AC_click_mouse",
                     "input": {"mouse_keycode": "mouse_left", "x": 149, "y": 75}}

    second = backend.decide_next_action("goal", screen, [_step(0, "AC_click_mouse")])
    assert second == {"tool": "AC_write", "input": {"write_string": "hi"}}
    assert len(client.messages.calls) == 1, "the batch's second call ran without a request"

    final = backend.decide_next_action("goal", screen, [_step(0, "AC_click_mouse"),
                                                        _step(1, "AC_write")])
    assert final == {"stop": True, "message": "done"}
    # The recorded messages list is the live conversation, so the model's
    # reply follows the answers by now.
    answers = client.messages.calls[1]["messages"][-2]
    assert answers["role"] == "user"
    assert [(r["tool_use_id"], r["toolset_name"], r["is_error"]) for r in answers["content"]] == [
        ("t1", "computer", False), ("t2", "computer", False)]


def test_a_failed_step_answers_the_rest_of_the_batch_as_skipped():
    batch = _Response([
        _Block("tool_use", id="a", name="key", input={"text": "Return"}),
        _Block("tool_use", id="b", name="screenshot", input={}),
    ])
    done = _Response([_Block("text", text="gave up")], stop_reason="end_turn")
    backend, client = _toolset_backend([batch, done])
    backend.decide_next_action("goal", None, [])
    result = backend.decide_next_action("goal", None, [_step(0, "AC_type_keyboard", error="boom")])
    assert result["stop"] is True
    answers = client.messages.calls[1]["messages"][-2]["content"]
    assert [(r["tool_use_id"], r["is_error"]) for r in answers] == [("a", True), ("b", True)]
    assert "not run" in answers[1]["content"][0]["text"]


def test_an_unknown_member_is_refused():
    backend, _client = _toolset_backend([_Response([
        _Block("tool_use", id="z", name="teleport", input={})])])
    with pytest.raises(AgentBackendError, match="teleport"):
        backend.decide_next_action("goal", None, [])


def test_screenshots_are_fitted_into_the_image_limits():
    fitted, (sx, sy) = fit_screenshot(_png(3840, 2160))
    from PIL import Image
    with Image.open(io.BytesIO(fitted)) as image:
        width, height = image.size
    assert (width, height) == (2576, 1449)
    assert max(width, height) <= MAX_LONG_EDGE_PX
    assert visual_tokens(width, height) <= MAX_VISUAL_TOKENS
    assert sx == pytest.approx(width / 3840) and sy == pytest.approx(height / 2160)
    # A 1080p screen is inside the high-resolution tier: it goes as it is.
    full_hd = _png(1920, 1080)
    assert fit_screenshot(full_hd) == (full_hd, (1.0, 1.0))
    for size in [(5120, 1440), (1000, 8000), (2576, 2576)]:
        fitted, _scale = fit_screenshot(_png(*size))
        with Image.open(io.BytesIO(fitted)) as image:
            assert visual_tokens(*image.size) <= MAX_VISUAL_TOKENS
            assert max(image.size) <= MAX_LONG_EDGE_PX


def test_other_models_keep_the_beta_tool():
    backend = ComputerUseAgentBackend(display_width_px=100, display_height_px=100,
                                      client=object(), model="claude-opus-5")
    assert backend._tool_schema["type"] == "computer_20251124"  # noqa: SLF001


def test_a_drag_ends_at_coordinate():
    out = _decision_from_computer_action({
        "action": "left_click_drag", "start_coordinate": [1, 2], "coordinate": [30, 40]})
    assert out["input"]["action_list"][-1] == [
        "AC_release_mouse", {"mouse_keycode": "mouse_left", "x": 30, "y": 40}]


def test_key_repeat_presses_that_many_times():
    out = _decision_from_computer_action({"action": "key", "text": "Down", "repeat": 3})
    assert out["tool"] == "AC_execute_action"
    assert [action[0] for action in out["input"]["action_list"]] == ["AC_type_keyboard"] * 3
    single = _decision_from_computer_action({"action": "key", "text": "Down"})
    assert single["tool"] == "AC_type_keyboard"


def test_a_modifier_click_holds_the_modifier():
    out = _decision_from_computer_action({
        "action": "left_click", "coordinate": [5, 6], "text": "shift"})
    assert out["tool"] == "AC_with_modifiers"
    assert len(out["input"]["modifiers"]) == 1
    assert out["input"]["actions"] == [
        ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 5, "y": 6}]]


def test_zoom_answers_with_a_full_resolution_crop():
    from PIL import Image
    batch = _Response([
        _Block("tool_use", id="z1", name="zoom", input={"region": [100, 50, 300, 150]}),
        _Block("tool_use", id="c1", name="left_click", input={"coordinate": [200, 100]}),
    ])
    done = _Response([_Block("text", text="done")], stop_reason="end_turn")
    backend, client = _toolset_backend([batch, done])
    screen = _png(3840, 2160)
    first = backend.decide_next_action("goal", screen, [])
    assert first == {"tool": "AC_screenshot", "input": {}}
    second = backend.decide_next_action("goal", screen, [_step(0, "AC_screenshot")])
    # The click after a zoom is still in the full screenshot's space.
    assert second["input"]["x"] == 298 and second["input"]["y"] == 149
    backend.decide_next_action("goal", screen, [_step(0, "AC_screenshot"),
                                                _step(1, "AC_click_mouse")])
    answers = client.messages.calls[1]["messages"][-2]["content"]
    zoom_answer = answers[0]
    assert zoom_answer["tool_use_id"] == "z1" and not zoom_answer["is_error"]
    image_block = zoom_answer["content"][0]
    assert image_block["type"] == "image"
    data = base64.b64decode(image_block["source"]["data"])
    with Image.open(io.BytesIO(data)) as image:
        # Model region (100, 50)-(300, 150) at scale 2576/3840 is screen
        # (149, 74)-(448, 224), sent unscaled.
        assert image.size == (299, 150)


def test_a_malformed_zoom_is_a_backend_error():
    backend, _client = _toolset_backend([_Response([
        _Block("tool_use", id="z", name="zoom", input={"region": [1, 2]})])])
    with pytest.raises(AgentBackendError, match="zoom"):
        backend.decide_next_action("goal", None, [])
