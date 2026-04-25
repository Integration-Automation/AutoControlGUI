"""Shared types and helpers for the MCP tool registry.

Holds the public value types (:class:`MCPContent`,
:class:`MCPToolAnnotations`, :class:`MCPTool`), the JSON-Schema
helper, and the annotation constants used by every tool factory.
"""
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class MCPContent:
    """One content block returned to an MCP client.

    The ``type`` field follows the MCP content discriminator: ``text``,
    ``image``, or ``resource``. Tools normally return plain Python
    objects (auto-wrapped in a single ``text`` block); use this class
    when a tool needs to return non-text content such as a screenshot.
    """

    type: str
    text: Optional[str] = None
    data: Optional[str] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON shape MCP clients expect for one content block."""
        if self.type == "text":
            return {"type": "text", "text": self.text or ""}
        if self.type == "image":
            return {
                "type": "image", "data": self.data or "",
                "mimeType": self.mime_type or "image/png",
            }
        return {"type": self.type, "text": self.text or ""}

    @classmethod
    def text_block(cls, text: str) -> "MCPContent":
        return cls(type="text", text=text)

    @classmethod
    def image_block(cls, data: str,
                    mime_type: str = "image/png") -> "MCPContent":
        return cls(type="image", data=data, mime_type=mime_type)


@dataclass(frozen=True)
class MCPToolAnnotations:
    """MCP behaviour hints surfaced to the client per the 2025-03-26 spec.

    Defaults follow the spec: a tool is assumed to mutate state in an
    open world unless it explicitly opts in to read-only / closed-world.
    These hints are advisory — clients may use them to require user
    confirmation before destructive calls but MUST NOT rely on them for
    security.
    """

    title: Optional[str] = None
    read_only: bool = False
    destructive: bool = True
    idempotent: bool = False
    open_world: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON shape MCP clients expect under ``annotations``."""
        annotations: Dict[str, Any] = {
            "readOnlyHint": self.read_only,
            "destructiveHint": False if self.read_only else self.destructive,
            "idempotentHint": self.idempotent,
            "openWorldHint": self.open_world,
        }
        if self.title is not None:
            annotations["title"] = self.title
        return annotations


@dataclass(frozen=True)
class MCPTool:
    """A single MCP tool — public name, schema, and Python callable."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    annotations: MCPToolAnnotations = MCPToolAnnotations()

    def to_descriptor(self) -> Dict[str, Any]:
        """Return the dict shape MCP clients expect from ``tools/list``."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": self.annotations.to_dict(),
        }

    def invoke(self, arguments: Dict[str, Any]) -> Any:
        """Call the underlying handler with keyword arguments."""
        return self.handler(**arguments)


def schema(properties: Dict[str, Any],
           required: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build a JSON Schema object node from a property mapping."""
    node: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        node["required"] = list(required)
    return node


# Pre-built annotation singletons used by every tool factory.
DESTRUCTIVE = MCPToolAnnotations(destructive=True)
NON_DESTRUCTIVE = MCPToolAnnotations(destructive=False, idempotent=True)
READ_ONLY = MCPToolAnnotations(read_only=True, idempotent=True)
SIDE_EFFECT_ONLY = MCPToolAnnotations(destructive=False, idempotent=False)


def read_only_env_flag() -> bool:
    """Return True when JE_AUTOCONTROL_MCP_READONLY is set to a truthy value."""
    raw = os.environ.get("JE_AUTOCONTROL_MCP_READONLY", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}
