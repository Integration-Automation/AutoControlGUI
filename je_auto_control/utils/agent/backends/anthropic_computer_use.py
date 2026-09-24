"""Anthropic Computer-Use tool backend.

Bridges Anthropic's computer-use tool to AutoControl's executor, in either of
its two request shapes:

* the beta ``computer_20251124`` tool (the default): one ``computer`` call per
  turn with an ``action`` field (``screenshot`` / ``left_click`` / ...);
* the GA ``computer_toolset_20260801`` (chosen automatically for models that
  accept nothing else, such as ``claude-opus-5-5``): one call per member name,
  possibly several per turn; see :mod:`._computer_toolset`.

Either way each action becomes the equivalent ``AC_*`` invocation.

Why a second backend? :mod:`anthropic.py` exposes our full ``AC_*``
schema and lets the model pick any of ~100 tools. That works, but it
foregoes Claude's specifically-trained computer-use behaviour. With
this backend the model uses the official spec — chain-of-thought,
coordinate handling, and tool ergonomics that match Anthropic's
training distribution — and we only run the canonical ``AC_*`` calls.

See https://docs.claude.com/en/docs/build-with-claude/computer-use for
the upstream tool schema (action verbs, payload shape, screenshot
return).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.agent.agent_loop import AgentBackend, AgentStep
from je_auto_control.utils.agent.backends._computer_toolset import (
    TOOLSET_ONLY_MODELS, TOOLSET_SCHEMA, TOOLSET_TYPE, ToolsetBatch,
    fit_screenshot, unscale_decision,
)
from je_auto_control.utils.agent.backends.base import (
    REQUEST_TIMEOUT_S, AgentBackendError, build_default_system_prompt,
    encode_screenshot_b64, prune_old_screenshots,
)


_DEFAULT_MODEL = "claude-opus-5"
_DEFAULT_TOOL_TYPE = "computer_20251124"

#: The beta each computer-use tool version is sent under. Every version is
#: beta-only: posted through the plain ``messages.create`` without one, the
#: API rejects the request, so the backend could never run.
_TOOL_BETAS = {
    "computer_20250124": "computer-use-2025-01-24",
    "computer_20251124": "computer-use-2025-11-24",
}

#: Upper bounds on what one model action may ask for. The spec caps ``wait``
#: at 100 s; a hold longer than that, or a scroll of more notches, is not a
#: step an agent needs, and an unbounded scroll overflowed the platform call.
_MAX_WAIT_S = 100.0
_MAX_SCROLL_NOTCHES = 100
_MAX_KEY_REPEAT = 100


# Map xdotool-style key names (used by Anthropic's tool spec) to the
# names AutoControl's keyboard wrappers expect. Anything outside this
# table is forwarded as-is; the wrapper rejects unknown keys cleanly.
_XDOTOOL_KEY_ALIAS = {
    "return": "enter",
    "escape": "esc",
    "page_up": "pageup",
    "page_down": "pagedown",
    "back_space": "backspace",
    "bksp": "backspace",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "super_l": "win",
    "super_r": "win",
    "meta_l": "win",
    "meta_r": "win",
}


def _normalise_key(name: str) -> str:
    """This platform's name for an xdotool key.

    The fixed aliases ("return" -> "enter", "escape" -> "esc", "page_down" ->
    "pagedown") are not names the Windows key table knows, so Enter, Esc,
    paging, Alt and Super failed there; cua_action's resolver knows each
    platform's spelling.
    """
    from je_auto_control.utils.cua_action.cua_action import resolve_key_name
    return resolve_key_name(_XDOTOOL_KEY_ALIAS.get(name.lower(), name.lower()))


def _parse_combo(combo: str) -> List[str]:
    """Split an xdotool-style hotkey (``ctrl+shift+T``) into key names."""
    return [_normalise_key(p) for p in combo.split("+") if p.strip()]


def _click_button(action: str) -> str:
    return {
        "left_click": "mouse_left",
        "right_click": "mouse_right",
        "middle_click": "mouse_middle",
        "double_click": "mouse_left",
        "triple_click": "mouse_left",
    }.get(action, "mouse_left")


def _click_repeats(action: str) -> int:
    return {"double_click": 2, "triple_click": 3}.get(action, 1)


class ComputerUseAgentBackend(AgentBackend):
    """Drive ``AgentLoop`` through Anthropic's native computer-use tool.

    The backend exposes the beta ``computer`` tool or the GA computer
    toolset, translates each action into ``AC_*`` calls via the executor, and
    threads each ``tool_result`` back so the model can continue the loop.
    """

    def __init__(self,
                 *,
                 display_width_px: int,
                 display_height_px: int,
                 display_number: Optional[int] = None,
                 client: Optional[Any] = None,
                 api_key: Optional[str] = None,
                 model: str = _DEFAULT_MODEL,
                 tool_type: Optional[str] = None,
                 beta: Optional[str] = None,
                 max_tokens: int = 1024,
                 system_prompt_builder: Optional[Callable[[str], str]] = None,
                 ) -> None:
        """``tool_type`` defaults to the toolset for models that take only
        that (``claude-opus-5-5``) and to ``computer_20251124`` otherwise; the
        display size still bounds every coordinate in toolset mode."""
        if display_width_px <= 0 or display_height_px <= 0:
            raise AgentBackendError(
                "display_width_px / display_height_px must be positive",
            )
        self._display = (int(display_width_px), int(display_height_px))
        tool_type = tool_type or (TOOLSET_TYPE if model in TOOLSET_ONLY_MODELS
                                  else _DEFAULT_TOOL_TYPE)
        self._batch: Optional[ToolsetBatch] = None
        self._scale = (1.0, 1.0)
        if tool_type == TOOLSET_TYPE:
            # GA: no beta, no name, no display size.
            self._batch = ToolsetBatch()
            self._tool_schema: Dict[str, Any] = dict(TOOLSET_SCHEMA)
            self._beta: Optional[str] = None
        else:
            self._tool_schema = {
                "type": tool_type, "name": "computer",
                "display_width_px": self._display[0],
                "display_height_px": self._display[1],
            }
            if display_number is not None:
                self._tool_schema["display_number"] = int(display_number)
            self._beta = beta or _TOOL_BETAS.get(tool_type)
            if not self._beta:
                raise AgentBackendError(
                    f"no known beta for computer-use tool {tool_type!r}; pass beta=")
        self._client = client
        self._api_key = api_key
        self._model = model
        self._max_tokens = int(max_tokens)
        self._build_system = (
            system_prompt_builder or build_default_system_prompt
        )
        self._conversation: List[Dict[str, Any]] = []
        self._pending_tool_use_id: Optional[str] = None

    # --- public AgentBackend protocol --------------------------------

    def decide_next_action(self,
                            goal: str,
                            screenshot: Optional[bytes],
                            history: Sequence[AgentStep],
                            ) -> Dict[str, Any]:
        if self._batch is not None:
            return self._decide_with_toolset(self._batch, goal, screenshot, history)
        self._ingest_history(history, screenshot)
        if not self._conversation:
            self._conversation.append({
                "role": "user",
                "content": _initial_user_content(goal, screenshot),
            })
        prune_old_screenshots(self._conversation)
        return self._handle_response(self._create(goal, beta=True))

    def _create(self, goal: str, *, beta: bool) -> Any:
        """One Messages API call with the current conversation."""
        client = self._resolve_client()
        request: Dict[str, Any] = {
            "timeout": REQUEST_TIMEOUT_S, "model": self._model,
            "system": self._build_system(goal), "tools": [self._tool_schema],
            "messages": self._conversation, "max_tokens": self._max_tokens,
        }
        try:
            if not beta:
                return client.messages.create(**request)
            # This path answers exactly one tool_use per turn, so parallel
            # tool use must stay off: a second computer tool_use would be left
            # unanswered and the next create() would 400 on the dangling id.
            return client.beta.messages.create(
                betas=[self._beta],
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                **request)
        except Exception as exc:  # noqa: BLE001  # reason: rewrap to backend error
            raise AgentBackendError(
                f"anthropic computer-use call failed: {exc}",
            ) from exc

    # --- toolset (computer_toolset_20260801) ---------------------------

    def _decide_with_toolset(self, batch: ToolsetBatch, goal: str,
                             screenshot: Optional[bytes],
                             history: Sequence[AgentStep]) -> Dict[str, Any]:
        """Run the turn's queued calls first; ask the model once all are answered."""
        if batch.inflight is not None and history:
            last = history[-1]
            batch.record(self._toolset_result_content(last, screenshot), bool(last.error))
        if batch.has_next():
            return batch.next_decision()
        results = batch.drain_results()
        if results:
            self._conversation.append({"role": "user", "content": results})
        if not self._conversation:
            self._conversation.append({
                "role": "user",
                "content": _initial_user_content(goal, self._fit(screenshot)),
            })
        prune_old_screenshots(self._conversation)
        return self._handle_toolset_response(self._create(goal, beta=False), batch)

    def _fit(self, screenshot: Optional[bytes]) -> Optional[bytes]:
        """``screenshot`` within the toolset's image limits; remembers the scale."""
        if not screenshot:
            return screenshot
        fitted, self._scale = fit_screenshot(screenshot)
        return fitted

    def _toolset_result_content(self, step: AgentStep,
                                screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
        fitted = self._fit(screenshot) if step.tool == "AC_screenshot" else screenshot
        return _tool_result_content(step, fitted)

    def _handle_toolset_response(self, response: Any,
                                 batch: ToolsetBatch) -> Dict[str, Any]:
        content = list(getattr(response, "content", []) or [])
        self._conversation.append({"role": "assistant", "content": content})
        calls = [(_attr(block, "id"), self._toolset_decision(block))
                 for block in content if _block_type(block) == "tool_use"]
        if not calls:
            return _final_answer(response, content)
        batch.load(calls)
        return batch.next_decision()

    def _toolset_decision(self, block: Any) -> Dict[str, Any]:
        """A member call as a decision, in screen pixels and on the display."""
        name = str(_attr(block, "name") or "")
        if name not in _CLICK_ACTIONS and name not in _ACTION_HANDLERS:
            raise AgentBackendError(
                f"model called tool {name!r}; only computer toolset members were offered")
        payload = dict(_attr(block, "input") or {})
        payload["action"] = name       # the member name is the action
        decision = unscale_decision(_decision_from_computer_action(payload), self._scale)
        return _clamp_decision(decision, *self._display)

    # --- response → AgentLoop decision -------------------------------

    def _handle_response(self, response: Any) -> Dict[str, Any]:
        content = list(getattr(response, "content", []) or [])
        self._conversation.append({"role": "assistant", "content": content})
        for block in content:
            if _block_type(block) != "tool_use":
                continue
            name = _attr(block, "name")
            if name != "computer":
                # Skipping it made the turn look like a final answer: the run
                # reported success having done nothing the model asked for.
                raise AgentBackendError(
                    f"model called tool {name!r}; only 'computer' was offered",
                )
            payload = _attr(block, "input") or {}
            self._pending_tool_use_id = _attr(block, "id")
            return _clamp_decision(
                _decision_from_computer_action(payload), *self._display)
        return _final_answer(response, content)

    def _ingest_history(self, history: Sequence[AgentStep],
                        screenshot: Optional[bytes]) -> None:
        if not history or self._pending_tool_use_id is None:
            return
        last = history[-1]
        content = _tool_result_content(last, screenshot)
        self._conversation.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": self._pending_tool_use_id,
                "content": content,
                "is_error": bool(last.error),
            }],
        })
        self._pending_tool_use_id = None

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise AgentBackendError(
                "anthropic SDK not installed (pip install anthropic).",
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client


# --- action translation ---------------------------------------------

def _final_answer(response: Any, content: List[Any]) -> Dict[str, Any]:
    """A turn without tool calls: the final answer, unless it was cut short.

    The default max_tokens can be hit mid-plan, or the model may refuse; a
    truncated reply must not be reported as a successful final answer.
    """
    _raise_if_truncated(response)
    text_parts: List[str] = [
        _attr(b, "text") or ""
        for b in content if _block_type(b) == "text"
    ]
    return {"stop": True, "message": "\n".join(text_parts).strip()}


def _action_screenshot(_payload):
    return {"tool": "AC_screenshot", "input": {}}


def _action_cursor_position(_payload):
    return {"tool": "AC_get_mouse_position", "input": {}}


def _action_mouse_move(payload):
    x, y = _xy(payload.get("coordinate"))
    return {"tool": "AC_set_mouse_position", "input": {"x": x, "y": y}}


def _action_type(payload):
    return {
        "tool": "AC_write",
        "input": {"write_string": str(payload.get("text") or "")},
    }


def _action_wait(payload):
    duration = payload.get("duration")
    # An explicit 0 is a valid "don't wait" — only fall back when unset.
    seconds = _number(duration, "duration") if duration is not None else 1.0
    return _sequence([["AC_sleep", {"seconds": _bounded_seconds(seconds)}]])


def _bounded_seconds(seconds: float) -> float:
    """A model-chosen duration within ``[0, _MAX_WAIT_S]``.

    The run's wall-clock budget is checked between steps, so one unbounded
    ``wait`` or ``hold_key`` blocked far past it.
    """
    return min(max(float(seconds), 0.0), _MAX_WAIT_S)


_CLICK_ACTIONS = frozenset({
    "left_click", "right_click", "middle_click",
    "double_click", "triple_click",
})


def _decision_from_computer_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one ``computer`` tool payload into an ``AgentLoop`` decision."""
    action = str(payload.get("action") or "").lower()
    if action in _CLICK_ACTIONS:
        decision = _click_decision(action, payload.get("coordinate"))
    else:
        handler = _ACTION_HANDLERS.get(action)
        if handler is None:
            raise AgentBackendError(
                f"computer-use action {action!r} is not recognised",
            )
        decision = handler(payload)
    if action in _MODIFIER_ACTIONS and payload.get("text"):
        return _with_modifiers(decision, str(payload["text"]))
    return decision


#: Actions whose ``text`` names modifier keys to hold (``shift`` for a
#: shift-click). The field was ignored, so a ctrl-click was a plain click.
_MODIFIER_ACTIONS = _CLICK_ACTIONS | {"left_click_drag", "scroll"}


def _with_modifiers(decision: Dict[str, Any], combo: str) -> Dict[str, Any]:
    """Run ``decision`` with the keys of ``combo`` held; they are released even on failure."""
    keys = _parse_combo(combo)
    if not keys:
        return decision
    inner = decision["input"]
    actions = (inner["action_list"] if decision["tool"] == "AC_execute_action"
               else [[decision["tool"], inner]])
    return {"tool": "AC_with_modifiers",
            "input": {"modifiers": keys, "actions": actions}}


def _click_decision(action: str, coordinate) -> Dict[str, Any]:
    button = _click_button(action)
    repeats = _click_repeats(action)
    inputs: Dict[str, Any] = {"mouse_keycode": button}
    if coordinate is not None:
        x, y = _xy(coordinate)
        inputs["x"], inputs["y"] = x, y
    if repeats == 1:
        return {"tool": "AC_click_mouse", "input": inputs}
    # AC_click_mouse takes no repeat count (a 'repeat' argument made every
    # click a TypeError): move once, then click the given number of times.
    clicks = [["AC_click_mouse", inputs]]
    clicks += [["AC_click_mouse", {"mouse_keycode": button}]] * (repeats - 1)
    return _sequence(clicks)


def _sequence(actions: List[List[Any]]) -> Dict[str, Any]:
    """Run several executor actions as one step, failing the step on any error."""
    return {"tool": "AC_execute_action",
            "input": {"action_list": actions, "raise_on_error": True}}


def _drag_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    # The spec's end point is ``coordinate`` (``start_coordinate`` is the
    # start); reading only ``end_coordinate`` failed every drag the model made.
    start = payload.get("start_coordinate")
    end = payload.get("end_coordinate") or payload.get("coordinate")
    if start is None or end is None:
        raise AgentBackendError(
            "left_click_drag requires start_coordinate and coordinate",
        )
    sx, sy = _xy(start)
    ex, ey = _xy(end)
    # No AC_drag command exists: press at the start, move, release at the end.
    return _sequence([
        ["AC_press_mouse", {"mouse_keycode": "mouse_left", "x": sx, "y": sy}],
        ["AC_set_mouse_position", {"x": ex, "y": ey}],
        ["AC_release_mouse", {"mouse_keycode": "mouse_left", "x": ex, "y": ey}],
    ])


def _scroll_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    direction = str(payload.get("scroll_direction") or "down").lower()
    raw_amount = payload.get("scroll_amount")
    # An explicit 0 means "no scroll" — only default when the key is absent.
    amount = int(_number(raw_amount, "scroll_amount")) if raw_amount is not None else 3
    amount = min(max(amount, 0), _MAX_SCROLL_NOTCHES)
    delta = amount if direction == "up" else -amount
    inputs: Dict[str, Any] = {"scroll_value": delta}
    # The scroll happens where the model pointed, not wherever the cursor was;
    # _clamp_decision keeps the point on the display.
    if payload.get("coordinate") is not None:
        inputs["x"], inputs["y"] = _xy(payload["coordinate"])
    return {"tool": "AC_mouse_scroll", "input": inputs}


def _key_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    combo = str(payload.get("text") or payload.get("key") or "")
    keys = _parse_combo(combo)
    if not keys:
        raise AgentBackendError("key action missing 'text'")
    press = ({"tool": "AC_type_keyboard", "input": {"keycode": keys[0]}} if len(keys) == 1
             else {"tool": "AC_hotkey", "input": {"key_code_list": keys}})
    raw_repeat = payload.get("repeat")
    repeat = int(_number(raw_repeat, "repeat")) if raw_repeat is not None else 1
    repeat = min(max(repeat, 1), _MAX_KEY_REPEAT)
    if repeat == 1:
        return press
    # ``repeat`` (1..100) was ignored, so "press Down 5 times" pressed once.
    return _sequence([[press["tool"], press["input"]]] * repeat)


def _hold_key_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    key = _normalise_key(str(payload.get("text") or payload.get("key") or ""))
    if not key:
        raise AgentBackendError("hold_key action missing 'text'")
    duration = _bounded_seconds(_number(payload.get("duration") or 0.0, "duration"))
    return {
        "tool": "AC_hold_key",
        "input": {"key": key, "duration_s": duration},
    }


def _mouse_button_decision(tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map a bare press/release verb to an ``AC_press/release_mouse`` call."""
    inputs: Dict[str, Any] = {"mouse_keycode": "mouse_left"}
    coordinate = payload.get("coordinate")
    if coordinate is not None:
        inputs["x"], inputs["y"] = _xy(coordinate)
    return {"tool": tool, "input": inputs}


def _mouse_down_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _mouse_button_decision("AC_press_mouse", payload)


def _mouse_up_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _mouse_button_decision("AC_release_mouse", payload)


# Dispatch table — populated after every handler is defined so the
# table reads its targets at module load time.
_ACTION_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "screenshot": _action_screenshot,
    "cursor_position": _action_cursor_position,
    "mouse_move": _action_mouse_move,
    "type": _action_type,
    "wait": _action_wait,
    "left_click_drag": _drag_decision,
    "scroll": _scroll_decision,
    "key": _key_decision,
    "hold_key": _hold_key_decision,
    # computer_20250124 press/release verbs — without these an otherwise
    # valid action raised AgentBackendError outside the create() try and
    # aborted the run.
    "left_mouse_down": _mouse_down_decision,
    "left_mouse_up": _mouse_up_decision,
}


_TRUNCATION_STOP_REASONS = frozenset({"max_tokens", "refusal"})


def _raise_if_truncated(response: Any) -> None:
    """Reject an incomplete turn instead of treating it as a final answer."""
    stop_reason = _attr(response, "stop_reason")
    if stop_reason in _TRUNCATION_STOP_REASONS:
        raise AgentBackendError(
            "anthropic computer-use response was incomplete "
            f"(stop_reason={stop_reason!r})",
        )


# --- helpers --------------------------------------------------------

def _xy(coordinate: Any) -> Tuple[int, int]:
    if (not isinstance(coordinate, (list, tuple))
            or len(coordinate) != 2):
        raise AgentBackendError(
            f"coordinate must be [x, y]; got {coordinate!r}",
        )
    return int(_number(coordinate[0], "x")), int(_number(coordinate[1], "y"))


def _number(value: Any, what: str) -> float:
    """``value`` as a finite float, or :class:`AgentBackendError`."""
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AgentBackendError(f"{what} must be a number, got {value!r}") from error
    if not math.isfinite(number):
        raise AgentBackendError(f"{what} must be finite, got {value!r}")
    return number


def _clamp_decision(decision: Dict[str, Any], width: int, height: int) -> Dict[str, Any]:
    """Keep every ``x`` / ``y`` in the decision on the declared display.

    The model's coordinates went to the mouse unchecked: [-500, 99999] on a
    100x100 display was dispatched as given.
    """
    inputs = decision.get("input") or {}
    _clamp_inputs(inputs, width, height)
    for key in ("action_list", "actions"):
        for action in inputs.get(key) or []:
            if len(action) == 2 and isinstance(action[1], dict):
                _clamp_inputs(action[1], width, height)
    return decision


def _clamp_inputs(inputs: Dict[str, Any], width: int, height: int) -> None:
    if "x" in inputs:
        inputs["x"] = min(max(int(inputs["x"]), 0), width - 1)
    if "y" in inputs:
        inputs["y"] = min(max(int(inputs["y"]), 0), height - 1)


def _block_type(block: Any) -> Optional[str]:
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def _attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _initial_user_content(goal: str,
                           screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    encoded = encode_screenshot_b64(screenshot)
    if encoded:
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": encoded,
            },
        })
    blocks.append({"type": "text", "text": goal})
    return blocks


def _tool_result_content(step: AgentStep,
                         screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
    """Build a ``tool_result`` content payload for the last ``AC_*`` call.

    Anthropic's spec expects the screenshot tool to return the image
    *itself* — text-only results just describe what happened.
    """
    if step.error:
        return [{"type": "text", "text": f"error: {step.error}"}]
    if step.tool == "AC_screenshot":
        encoded = encode_screenshot_b64(screenshot)
        if encoded:
            return [{
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encoded,
                },
            }]
    text = repr(step.result) if step.result is not None else "ok"
    return [{"type": "text", "text": text[:4000]}]


__all__ = ["ComputerUseAgentBackend"]
