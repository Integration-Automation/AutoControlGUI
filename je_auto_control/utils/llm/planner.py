"""Plan ``AC_*`` action lists from natural-language descriptions.

The planner builds a system prompt describing the available command set,
asks the configured LLM backend to emit a JSON action list, then validates
the result with the same schema the executor uses. If the model wraps the
list in prose or a code fence, we extract the first JSON array we find.
"""
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.llm.backends import (
    LLMBackend, LLMNotAvailableError, get_backend,
)

_SYSTEM_PROMPT = (
    "You translate plain-language automation instructions into a strict "
    "JSON action list for the AutoControl executor.\n\n"
    "Rules:\n"
    "1. Output ONLY a JSON array. No prose, no code fences, no comments.\n"
    "2. Each element is [name] or [name, params]. ``params`` is an object.\n"
    "3. Use ONLY commands from the provided allowlist; do not invent names.\n"
    "4. Coordinates and counts are integers; thresholds are floats.\n"
    "5. Flow-control commands carry their nested actions inside ``body`` / "
    "``then`` / ``else``.\n"
    "6. Reference runtime variables with ``${name}`` strings; declare them "
    "with AC_set_var before use.\n"
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


class LLMPlanError(AutoControlActionException):
    """Raised when the LLM response is not a valid action list."""


def plan_actions(description: str,
                 known_commands: Iterable[str],
                 examples: Optional[List[Dict[str, Any]]] = None,
                 backend: Optional[LLMBackend] = None,
                 model: Optional[str] = None,
                 max_tokens: int = 2048) -> List[list]:
    """Translate ``description`` into a validated action list.

    ``examples`` is an optional list of ``{"description": ..., "actions": [...]}``
    pairs used as few-shot guidance. Raises :class:`LLMPlanError` when the
    model output is unparseable, empty, or references unknown commands.
    """
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    bound = backend if backend is not None else get_backend()
    if not bound.available:
        raise LLMNotAvailableError(
            "no LLM backend configured; set ANTHROPIC_API_KEY and install "
            "the matching SDK",
        )
    allowed = sorted(set(known_commands))
    if not allowed:
        raise ValueError("known_commands must list at least one command")
    prompt = _build_user_prompt(description, allowed, examples)
    raw = bound.complete(prompt, system=_SYSTEM_PROMPT, model=model,
                         max_tokens=max_tokens)
    actions = _parse_actions(raw)
    validate_actions(actions, allowed)
    return actions


def run_from_description(description: str,
                         executor: Any,
                         examples: Optional[List[Dict[str, Any]]] = None,
                         backend: Optional[LLMBackend] = None,
                         model: Optional[str] = None,
                         max_tokens: int = 2048) -> Dict[str, Any]:
    """Plan a description and execute it on ``executor`` in one call."""
    actions = plan_actions(
        description,
        known_commands=executor.known_commands(),
        examples=examples,
        backend=backend,
        model=model,
        max_tokens=max_tokens,
    )
    record = executor.execute_action(actions, _validated=True)
    return {"actions": actions, "record": record}


def _build_user_prompt(description: str,
                       allowed: List[str],
                       examples: Optional[List[Dict[str, Any]]]) -> str:
    """Compose the user-side prompt, including allowlist and few-shot."""
    parts = ["Allowed commands:"]
    parts.append(", ".join(allowed))
    if examples:
        parts.append("\nExamples:")
        for example in examples:
            desc = example.get("description", "").strip()
            actions = example.get("actions")
            if not desc or not isinstance(actions, list):
                continue
            parts.append(f"Description: {desc}")
            parts.append("Actions: " + json.dumps(actions, ensure_ascii=False))
    parts.append("\nDescription:")
    parts.append(description.strip())
    parts.append("\nReturn the JSON array now:")
    return "\n".join(parts)


def _parse_actions(raw: str) -> List[list]:
    """Extract a JSON array from ``raw`` and ensure it's a list of lists."""
    if not raw or not raw.strip():
        raise LLMPlanError("LLM returned empty response")
    candidate = _strip_code_fence(raw.strip())
    try:
        actions = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_ARRAY.search(candidate)
        if match is None:
            raise LLMPlanError(
                f"LLM output is not valid JSON: {raw[:200]!r}"
            ) from None
        try:
            actions = json.loads(match.group(0))
        except json.JSONDecodeError as error:
            raise LLMPlanError(
                f"LLM output JSON parse failed: {error}"
            ) from error
    if not isinstance(actions, list):
        raise LLMPlanError(
            f"LLM output must be a JSON array, got {type(actions).__name__}"
        )
    return actions


def _strip_code_fence(text: str) -> str:
    """Drop a leading/trailing markdown code fence if present."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
