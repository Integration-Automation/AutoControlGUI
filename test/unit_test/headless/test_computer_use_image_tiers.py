"""Computer-use screenshots fit the model's image tier on the beta tool too.

The API downscales a beta-tool screenshot over the model's image limits and
the model answers in the smaller image's pixels, but the backend declared the
real screen size and clicked the answer as is: on a 4K screen a click landed
at about two thirds of the intended position. Stub client only.
"""
import io
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends._computer_toolset import (
    HIGH_RES_TIER, STANDARD_TIER, image_tier, visual_tokens,
)
from je_auto_control.utils.agent.backends.anthropic_computer_use import ComputerUseAgentBackend

pytest.importorskip("PIL")


@dataclass
class _Block:
    type: str
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[Dict[str, Any]] = None


class _Response:
    def __init__(self, content):
        self.content = content
        self.stop_reason = "tool_use"


class _Messages:
    def __init__(self, script):
        self.calls = []
        self.script = list(script)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class _Client:
    def __init__(self, script):
        self.messages = _Messages(script)
        self.beta = type("Beta", (), {"messages": self.messages})()


def _png(width, height):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (1, 2, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


def _sent_image_size(request):
    import base64
    from PIL import Image
    block = request["messages"][0]["content"][0]
    with Image.open(io.BytesIO(base64.b64decode(block["source"]["data"]))) as image:
        return image.size


@pytest.mark.parametrize("model, tier", [
    ("claude-opus-4-7", HIGH_RES_TIER), ("claude-opus-5", HIGH_RES_TIER),
    ("claude-opus-5-5", HIGH_RES_TIER), ("anthropic.claude-opus-4-7-v1:0", HIGH_RES_TIER),
    ("claude-sonnet-4-5-20250929", STANDARD_TIER), ("claude-sonnet-4-20250514", STANDARD_TIER),
    ("claude-haiku-4-5-20251001", STANDARD_TIER), ("claude-3-5-sonnet-20241022", STANDARD_TIER),
    ("something-else", STANDARD_TIER),
])
def test_the_image_tier_follows_the_model(model, tier):
    assert image_tier(model) == tier


def _click_on(width, height, model):
    click = _Response([_Block("tool_use", id="t1", name="computer",
                              input={"action": "left_click", "coordinate": [1288, 724]})])
    client = _Client([click])
    backend = ComputerUseAgentBackend(display_width_px=width, display_height_px=height,
                                      client=client, model=model)
    decision = backend.decide_next_action("goal", _png(width, height), [])
    return decision, client.messages.calls[0]


def test_a_4k_screen_is_declared_and_shot_at_the_fitted_size():
    decision, request = _click_on(3840, 2160, "claude-opus-5")
    tool = request["tools"][0]
    assert (tool["display_width_px"], tool["display_height_px"]) == (2576, 1449)
    assert _sent_image_size(request) == (2576, 1449)
    # The model's (1288, 724) is the middle of the 2576x1449 image: the
    # middle of the screen.
    assert (decision["input"]["x"], decision["input"]["y"]) == (1920, 1079)


def test_a_standard_tier_model_gets_a_smaller_screen_on_1080p():
    decision, request = _click_on(1920, 1080, "claude-sonnet-4-5-20250929")
    tool = request["tools"][0]
    declared = (tool["display_width_px"], tool["display_height_px"])
    assert declared == _sent_image_size(request)
    assert max(declared) <= 1568 and visual_tokens(*declared) <= 1568
    assert declared[0] < 1920


def test_a_screen_inside_the_tier_is_left_alone():
    decision, request = _click_on(1920, 1080, "claude-opus-5")
    tool = request["tools"][0]
    assert (tool["display_width_px"], tool["display_height_px"]) == (1920, 1080)
    assert (decision["input"]["x"], decision["input"]["y"]) == (1288, 724)


def test_later_screenshots_are_resized_too():
    click = _Response([_Block("tool_use", id="t1", name="computer",
                              input={"action": "screenshot"})])
    done = _Response([_Block("text")])
    done.stop_reason = "end_turn"
    client = _Client([click, done])
    backend = ComputerUseAgentBackend(display_width_px=3840, display_height_px=2160,
                                      client=client, model="claude-opus-5")
    backend.decide_next_action("goal", _png(3840, 2160), [])
    step = AgentStep(index=0, tool="AC_screenshot", arguments={}, result=None)
    backend.decide_next_action("goal", _png(3840, 2160), [step])
    import base64
    from PIL import Image
    result = client.messages.calls[1]["messages"][-2]["content"][0]["content"][0]
    with Image.open(io.BytesIO(base64.b64decode(result["source"]["data"]))) as image:
        assert image.size == (2576, 1449)


@pytest.mark.parametrize("size, tier, expected", [
    ((1920, 1080), STANDARD_TIER, (1456, 819)),     # the vision docs' examples
    ((1075, 1520), STANDARD_TIER, (924, 1307)),
    ((1075, 1520), HIGH_RES_TIER, (1075, 1520)),
    ((3840, 2160), HIGH_RES_TIER, (2576, 1449)),
])
def test_fitted_sizes_match_the_documented_resize(size, tier, expected):
    from je_auto_control.utils.agent.backends._computer_toolset import fitted_size
    assert fitted_size(*size, tier) == expected


def test_the_generic_backend_fits_screenshots_and_maps_x_y_back():
    from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
    call = _Response([_Block("tool_use", id="t1", name="AC_click_mouse",
                             input={"mouse_keycode": "mouse_left", "x": 1288, "y": 724})])
    client = _Client([call])
    backend = AnthropicAgentBackend(
        tools=[{"name": "AC_click_mouse", "input_schema": {"type": "object"}}],
        client=client, model="claude-opus-4-7")
    decision = backend.decide_next_action("goal", _png(3840, 2160), [])
    assert _sent_image_size(client.messages.calls[0]) == (2576, 1449)
    assert (decision["input"]["x"], decision["input"]["y"]) == (1920, 1079)
