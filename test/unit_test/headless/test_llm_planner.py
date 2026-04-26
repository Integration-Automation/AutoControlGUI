"""Tests for the LLM action planner (no real LLM calls)."""
from typing import Optional

import pytest

from je_auto_control.utils.llm.backends.base import LLMBackend
from je_auto_control.utils.llm.planner import (
    LLMNotAvailableError, LLMPlanError, plan_actions, run_from_description,
)


class _StubBackend(LLMBackend):
    """Returns canned text and records the prompt for assertions."""

    name = "stub"

    def __init__(self, response: str, *, available: bool = True) -> None:
        self.available = available
        self.response = response
        self.last_prompt: Optional[str] = None
        self.last_system: Optional[str] = None
        self.last_model: Optional[str] = None

    def complete(self, prompt: str, system=None, model=None,
                 max_tokens: int = 2048) -> str:
        self.last_prompt = prompt
        self.last_system = system
        self.last_model = model
        return self.response


_KNOWN = {"AC_click_mouse", "AC_type_keyboard", "AC_set_var", "AC_loop"}


def test_plan_actions_returns_validated_list():
    backend = _StubBackend(
        '[["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]'
    )
    actions = plan_actions("click", known_commands=_KNOWN, backend=backend)
    assert actions == [["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]


def test_plan_actions_strips_code_fence():
    backend = _StubBackend(
        '```json\n[["AC_click_mouse"]]\n```'
    )
    actions = plan_actions("click", known_commands=_KNOWN, backend=backend)
    assert actions == [["AC_click_mouse"]]


def test_plan_actions_extracts_json_when_wrapped_in_prose():
    backend = _StubBackend(
        'Sure! Here is the plan: [["AC_click_mouse"]] hope it helps.'
    )
    actions = plan_actions("click", known_commands=_KNOWN, backend=backend)
    assert actions == [["AC_click_mouse"]]


def test_plan_actions_rejects_unknown_command():
    backend = _StubBackend('[["AC_does_not_exist"]]')
    with pytest.raises(Exception):
        plan_actions("x", known_commands=_KNOWN, backend=backend)


def test_plan_actions_rejects_non_array_response():
    backend = _StubBackend('{"not": "an array"}')
    with pytest.raises(LLMPlanError):
        plan_actions("x", known_commands=_KNOWN, backend=backend)


def test_plan_actions_rejects_empty_response():
    backend = _StubBackend("")
    with pytest.raises(LLMPlanError):
        plan_actions("x", known_commands=_KNOWN, backend=backend)


def test_plan_actions_unavailable_backend_raises():
    backend = _StubBackend("[]", available=False)
    with pytest.raises(LLMNotAvailableError):
        plan_actions("x", known_commands=_KNOWN, backend=backend)


def test_plan_actions_rejects_blank_description():
    backend = _StubBackend("[]")
    with pytest.raises(ValueError):
        plan_actions("   ", known_commands=_KNOWN, backend=backend)


def test_prompt_lists_allowed_commands_and_description():
    backend = _StubBackend("[]")
    try:
        plan_actions("type hello", known_commands=_KNOWN, backend=backend)
    except LLMPlanError:
        pass  # we only care about the prompt
    assert backend.last_prompt is not None
    assert "type hello" in backend.last_prompt
    for command in _KNOWN:
        assert command in backend.last_prompt


def test_prompt_includes_examples_when_provided():
    backend = _StubBackend("[]")
    examples = [{
        "description": "click left",
        "actions": [["AC_click_mouse"]],
    }]
    try:
        plan_actions("x", known_commands=_KNOWN, backend=backend,
                     examples=examples)
    except LLMPlanError:
        pass
    assert "click left" in backend.last_prompt
    assert "AC_click_mouse" in backend.last_prompt


def test_run_from_description_executes_plan():
    backend = _StubBackend('[["AC_noop"]]')

    class FakeExecutor:
        def __init__(self):
            self.executed = None

        def known_commands(self):
            return {"AC_noop"}

        def execute_action(self, actions, _validated=False):
            self.executed = actions
            return {"ok": True}

    fake = FakeExecutor()
    result = run_from_description("noop please", executor=fake, backend=backend)
    assert fake.executed == [["AC_noop"]]
    assert result["actions"] == [["AC_noop"]]
    assert result["record"] == {"ok": True}


def test_planner_passes_model_through_to_backend():
    backend = _StubBackend("[]")
    try:
        plan_actions("x", known_commands=_KNOWN, backend=backend,
                     model="claude-sonnet-4-6")
    except LLMPlanError:
        pass
    assert backend.last_model == "claude-sonnet-4-6"
