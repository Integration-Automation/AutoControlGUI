"""Local-model schemas expose observation references without changing legacy executor signatures."""
from __future__ import annotations

from typing import Any, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.observation_refs import POINT_TOOLS, validate_reference

REFERENCE_SCHEMA = {"oneOf": [
    {"type": "object", "properties": {"element_index": {"type": "integer", "minimum": 0}},
     "required": ["element_index"], "additionalProperties": False},
    {"type": "object", "properties": {"image_point": {"type": "array", "items": {"type": "number"},
                                                       "minItems": 2, "maxItems": 2}},
     "required": ["image_point"], "additionalProperties": False},
]}


def offered_tools(names: Sequence[str]) -> list[dict]:
    """Clone offered schemas and add a host-resolved target option only to reviewed point tools."""
    from je_auto_control.utils.tool_use_schema import export_openai_tools
    tools = detached(export_openai_tools(only=list(names)))
    if len(tools) != len(set(names)) or len(tools) > 32:
        raise AgentTaskError("a local task requires at most 32 known offered tools")
    for tool in tools:
        function = tool["function"]
        if function["name"] in POINT_TOOLS:
            _point_schema(function)
    return tools


def _point_schema(function: dict[str, Any]) -> None:
    parameters = function.setdefault("parameters", {"type": "object"})
    parameters.setdefault("properties", {})["observed_target"] = detached(REFERENCE_SCHEMA)
    parameters["required"] = [name for name in parameters.get("required", []) if name not in {"x", "y"}]
    parameters.setdefault("allOf", []).append({"anyOf": [
        {"required": ["observed_target"]}, {"required": ["x", "y"]},
    ]})


def referenced_proposal(name: str, arguments: dict) -> dict:
    """Separate reserved model reference data from real executor keyword arguments."""
    arguments = detached(arguments)
    reference = arguments.pop("observed_target", None)
    if reference is None:
        return {"tool": name, "arguments": arguments}
    if name not in POINT_TOOLS:
        raise AgentTaskError("observation reference was proposed for an incompatible tool")
    validate_reference(reference)
    return {"tool": name, "arguments": arguments, "reference": reference}
