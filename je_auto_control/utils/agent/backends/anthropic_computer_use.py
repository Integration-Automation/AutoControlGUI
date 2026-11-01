"""Anthropic Computer-Use tool backend.

Bridges Anthropic's computer-use tool to AutoControl's executor, in either of
its two request shapes:

* the beta ``computer_20251124`` tool (the default): one ``computer`` call per
  turn with an ``action`` field (``screenshot`` / ``left_click`` / ...);
* the GA ``computer_toolset_20260801`` (chosen automatically for models that
  accept nothing else, such as ``claude-opus-5-5``): one call per member name,
  possibly several per turn; see :mod:`._computer_toolset`.

Either way each action becomes the equivalent ``AC_*`` invocation.

Layout. This module is the backend itself: construction, the conversation and
the API call. The two request shapes are read in :mod:`._computer_beta_path`
and :mod:`._computer_toolset_path`; turning an action into ``AC_*`` calls is
:mod:`._computer_actions`, and the message blocks are
:mod:`._computer_messages`. The private names tests and callers import from
here are re-exported below.

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
from je_auto_control.utils.agent.backends._computer_actions import (  # noqa: F401  # reason: re-exported
    _ACTION_HANDLERS, _CLICK_ACTIONS, _MAX_KEY_REPEAT, _MAX_SCROLL_NOTCHES,
    _MAX_WAIT_S, _action_wait, _clamp_decision, _decision_from_computer_action,
    _hold_key_decision, _normalise_key, _parse_combo, _scroll_decision,
)
from je_auto_control.utils.agent.backends._computer_beta_path import (  # noqa: F401  # reason: re-exported
    _DEFAULT_TOOL_TYPE, _TOOL_BETAS, BetaToolPath, beta_for,
)
from je_auto_control.utils.agent.backends._computer_messages import (  # noqa: F401  # reason: re-exported
    _initial_user_content, _tool_result_content,
)
from je_auto_control.utils.agent.backends._computer_toolset import (
    TOOLSET_ONLY_MODELS, TOOLSET_SCHEMA, TOOLSET_TYPE, ToolsetBatch,
    fitted_size, image_tier, resize_png,
)
from je_auto_control.utils.agent.backends._computer_toolset_path import ToolsetPath
from je_auto_control.utils.agent.backends.base import (
    REQUEST_TIMEOUT_S, AgentBackendError, build_default_system_prompt,
    compact_history, image_block, needs_compaction, summarise_steps,
)


_DEFAULT_MODEL = "claude-opus-5"


class ComputerUseAgentBackend(BetaToolPath, ToolsetPath, AgentBackend):
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
        self._tier = image_tier(model)
        #: Beta tool only: the display size declared to the model, which every
        #: screenshot is resized to (``None`` for the toolset).
        self._declared: Optional[Tuple[int, int]] = None
        #: tool_use id -> the region a queued ``zoom`` asked for, in screenshot pixels.
        self._zooms: Dict[str, Tuple[int, int, int, int]] = {}
        if tool_type == TOOLSET_TYPE:
            # GA: no beta, no name, no display size.
            self._batch = ToolsetBatch()
            self._tool_schema: Dict[str, Any] = dict(TOOLSET_SCHEMA)
            self._beta: Optional[str] = None
        else:
            # The API downscales a screenshot over the model's image limits and
            # the model then answers in the smaller image's pixels, so the
            # screen is declared (and shot) at the fitted size and coordinates
            # are mapped back: on a 4K screen a click used to land at about
            # two thirds of the intended position.
            self._declared = fitted_size(*self._display, self._tier)
            self._scale = (self._declared[0] / self._display[0],
                           self._declared[1] / self._display[1])
            self._tool_schema = {
                "type": tool_type, "name": "computer",
                "display_width_px": self._declared[0],
                "display_height_px": self._declared[1],
            }
            if display_number is not None:
                self._tool_schema["display_number"] = int(display_number)
            self._beta = beta_for(tool_type, beta)
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
        if not history:
            self._new_run()
        if self._batch is not None:
            return self._decide_with_toolset(self._batch, goal, screenshot, history)
        if screenshot and self._declared is not None:
            screenshot = resize_png(screenshot, self._declared)
        self._extend(self._pending_result(history, screenshot), goal, screenshot, history)
        return self._handle_response(self._create(goal, beta=True))

    def _extend(self, results: List[Dict[str, Any]], goal: str,
                screenshot: Optional[bytes], history: Sequence[AgentStep]) -> None:
        """Append the turn's ``tool_result`` blocks, or start a new history.

        Sent turns are never edited: replacing their screenshots broke the
        prompt cache every step and, where thinking blocks are bound to the
        conversation before them, the request itself. Past the screenshot
        limit the history restarts from a summary and the current full
        screenshot (``screenshot``, already fitted) — the results are in the
        summary, since their ``tool_use`` blocks are not replayed.
        """
        if results and needs_compaction(self._conversation, results):
            self._conversation = compact_history(
                self._conversation, summarise_steps(goal, history), image_block(screenshot))
        elif results:
            self._conversation.append({"role": "user", "content": results})
        if not self._conversation:
            self._conversation.append({
                "role": "user",
                "content": _initial_user_content(goal, screenshot),
            })

    def _new_run(self) -> None:
        """Forget the previous run: its conversation ended on an unanswered tool_use."""
        self._conversation = []
        self._pending_tool_use_id = None
        self._zooms.clear()
        if self._batch is not None:
            self._batch = ToolsetBatch()

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
            content = self._toolset_result_content(last, screenshot, batch.inflight)
            batch.record(content, bool(last.error))
        if batch.has_next():
            return batch.next_decision()
        results = batch.drain_results()
        if not self._conversation or needs_compaction(self._conversation, results):
            # Only a history that opens with this frame takes its scale.
            screenshot = self._fit(screenshot)
        self._extend(results, goal, screenshot, history)
        return self._handle_toolset_response(self._create(goal, beta=False), batch)

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


__all__ = ["ComputerUseAgentBackend"]
