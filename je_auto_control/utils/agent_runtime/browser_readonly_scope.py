"""Narrow a frozen browser to a host-admitted verification scope without replacing input authority."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def _fixed(value: dict) -> str:
    result = dict(value)
    result.pop("roots")
    options = dict(result["options"])
    options.pop("origin_policies", None)
    result["options"] = options
    return json.dumps(result, sort_keys=True, allow_nan=False)


def readonly_verification_scope(original: Any, proposed: Any) -> None:
    """Accept only the exact original criteria/tools/options, no actions, and roots inside its ceiling.

    Current origin-policy IDs are supplied only by the host's privately admitted completion binding;
    the caller validates them live. Both arguments are already parsed task specifications.
    The old input specification and actual SDK context remain immutable.
    """
    expected = original.to_dict()
    expected.update(goal="Reviewed completion: " + original.goal[:15940], mode="external", actions=[])
    for key in ("dag_batch", "skill_pin"):
        expected["options"].pop(key, None)
    if _fixed(proposed.to_dict()) != _fixed(expected):
        raise AgentTaskError("read-only browser scope changed original permissions or completion evidence")
    if any(not any(Path(root).is_relative_to(Path(ceiling)) for ceiling in original.roots)
           for root in proposed.roots):
        raise AgentTaskError("read-only browser scope exceeds original roots")
