"""Anthropic Computer-Use tool backend.

Bridges Anthropic's official ``computer_20250124`` tool to AutoControl's
executor: the model issues one ``computer`` tool call per turn with an
``action`` field (``screenshot`` / ``left_click`` / ``type`` / ...)
and this backend translates it into the equivalent ``AC_*`` action
invocation.

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

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.agent.agent_loop import AgentBackend, AgentStep
from je_auto_control.utils.agent.backends.base import (
    AgentBackendError, build_default_system_prompt, encode_screenshot_b64,
)


_DEFAULT_MODEL = "claude-opus-4-7"
_DEFAULT_TOOL_TYPE = "computer_20250124"


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
    return _XDOTOOL_KEY_ALIAS.get(name.lower(), name.lower())


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
    """Drive ``AgentLoop`` through Anthropic's native ``computer_20250124``.

    The backend exposes one tool to the model, translates its action
    verbs into ``AC_*`` calls via the executor, and threads each
    ``tool_result`` back so the model can continue the loop.
    """

    def __init__(self,
                 *,
                 display_width_px: int,
                 display_height_px: int,
                 display_number: Optional[int] = None,
                 client: Optional[Any] = None,
                 api_key: Optional[str] = None,
                 model: str = _DEFAULT_MODEL,
                 tool_type: str = _DEFAULT_TOOL_TYPE,
                 max_tokens: int = 1024,
                 system_prompt_builder: Optional[Callable[[str], str]] = None,
                 ) -> None:
        if display_width_px <= 0 or display_height_px <= 0:
            raise AgentBackendError(
                "display_width_px / display_height_px must be positive",
            )
        self._tool_schema: Dict[str, Any] = {
            "type": tool_type,
            "name": "computer",
            "display_width_px": int(display_width_px),
            "display_height_px": int(display_height_px),
        }
        if display_number is not None:
            self._tool_schema["display_number"] = int(display_number)
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
        self._ingest_history(history, screenshot)
        if not self._conversation:
            self._conversation.append({
                "role": "user",
                "content": _initial_user_content(goal, screenshot),
            })
        client = self._resolve_client()
        try:
            response = client.messages.create(
                model=self._model,
                system=self._build_system(goal),
                tools=[self._tool_schema],
                messages=self._conversation,
                max_tokens=self._max_tokens,
                # This loop answers exactly one tool_use per turn, so parallel
                # tool use must stay off: a response with two computer tool_use
                # blocks would leave the second unanswered and the next
                # create() would 400 on the dangling tool_use id, aborting the
                # run. Mirror AnthropicAgentBackend's fix.
                tool_choice={
                    "type": "auto",
                    "disable_parallel_tool_use": True,
                },
            )
        except Exception as exc:  # noqa: BLE001  rewrap to backend error
            raise AgentBackendError(
                f"anthropic computer-use call failed: {exc}",
            ) from exc
        return self._handle_response(response)

    # --- response → AgentLoop decision -------------------------------

    def _handle_response(self, response: Any) -> Dict[str, Any]:
        content = list(getattr(response, "content", []) or [])
        self._conversation.append({"role": "assistant", "content": content})
        for block in content:
            if _block_type(block) != "tool_use":
                continue
            name = _attr(block, "name")
            if name != "computer":
                continue
            payload = _attr(block, "input") or {}
            self._pending_tool_use_id = _attr(block, "id")
            return _decision_from_computer_action(payload)
        # No tool_use → final answer + stop, unless the turn was cut short
        # (default max_tokens can be hit mid-plan, or the model may refuse):
        # a truncated reply must not be reported as a successful final answer.
        _raise_if_truncated(response)
        text_parts: List[str] = [
            _attr(b, "text") or ""
            for b in content if _block_type(b) == "text"
        ]
        return {"stop": True, "message": "\n".join(text_parts).strip()}

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
    seconds = float(duration) if duration is not None else 1.0
    return {"tool": "AC_sleep", "input": {"seconds": seconds}}


_CLICK_ACTIONS = frozenset({
    "left_click", "right_click", "middle_click",
    "double_click", "triple_click",
})


def _decision_from_computer_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one ``computer`` tool payload into an ``AgentLoop`` decision."""
    action = str(payload.get("action") or "").lower()
    if action in _CLICK_ACTIONS:
        return _click_decision(action, payload.get("coordinate"))
    handler = _ACTION_HANDLERS.get(action)
    if handler is None:
        raise AgentBackendError(
            f"computer-use action {action!r} is not recognised",
        )
    return handler(payload)


def _click_decision(action: str, coordinate) -> Dict[str, Any]:
    button = _click_button(action)
    repeats = _click_repeats(action)
    inputs: Dict[str, Any] = {"mouse_keycode": button, "repeat": repeats}
    if coordinate is not None:
        x, y = _xy(coordinate)
        inputs["x"], inputs["y"] = x, y
    return {"tool": "AC_click_mouse", "input": inputs}


def _drag_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    start = payload.get("start_coordinate") or payload.get("coordinate")
    end = payload.get("end_coordinate")
    if start is None or end is None:
        raise AgentBackendError(
            "left_click_drag requires start_coordinate + end_coordinate",
        )
    sx, sy = _xy(start)
    ex, ey = _xy(end)
    return {
        "tool": "AC_drag",
        "input": {
            "start_x": sx, "start_y": sy,
            "end_x": ex, "end_y": ey,
            "mouse_keycode": "mouse_left",
        },
    }


def _scroll_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    direction = str(payload.get("scroll_direction") or "down").lower()
    raw_amount = payload.get("scroll_amount")
    # An explicit 0 means "no scroll" — only default when the key is absent.
    amount = int(raw_amount) if raw_amount is not None else 3
    delta = amount if direction == "up" else -amount
    return {"tool": "AC_mouse_scroll", "input": {"scroll_value": delta}}


def _key_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    combo = str(payload.get("text") or payload.get("key") or "")
    keys = _parse_combo(combo)
    if not keys:
        raise AgentBackendError("key action missing 'text'")
    if len(keys) == 1:
        return {"tool": "AC_type_keyboard", "input": {"keycode": keys[0]}}
    return {"tool": "AC_hotkey", "input": {"key_code_list": keys}}


def _hold_key_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    key = _normalise_key(str(payload.get("text") or payload.get("key") or ""))
    if not key:
        raise AgentBackendError("hold_key action missing 'text'")
    duration = float(payload.get("duration") or 0.0)
    return {
        "tool": "AC_hold_key",
        "input": {"keycode": key, "duration": duration},
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
    return int(coordinate[0]), int(coordinate[1])


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
