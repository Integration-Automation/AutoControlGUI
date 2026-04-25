"""MCP resource providers for AutoControl.

Resources let an MCP client browse data the server has to offer
without invoking a tool — typical use cases here are listing the
JSON action library on disk, fetching the run-history snapshot, and
inspecting which executor commands the model can call. The provider
abstraction lets callers compose custom sources without touching the
JSON-RPC layer.
"""
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MCPResource:
    """One resource entry surfaced to MCP clients via ``resources/list``."""

    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None

    def to_descriptor(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {"uri": self.uri, "name": self.name}
        if self.description is not None:
            descriptor["description"] = self.description
        if self.mime_type is not None:
            descriptor["mimeType"] = self.mime_type
        return descriptor


class ResourceProvider:
    """Pluggable source. Subclasses override :meth:`list` and :meth:`read`."""

    def list(self) -> List[MCPResource]:  # pragma: no cover - abstract
        raise NotImplementedError

    def read(self, uri: str) -> Optional[Dict[str, Any]]:  # pragma: no cover - abstract
        """Return one content block (``{uri, mimeType, text}``) or ``None``."""
        raise NotImplementedError


class FileSystemProvider(ResourceProvider):
    """Expose ``*.json`` action files in ``root`` under ``<scheme>://files/<name>``."""

    def __init__(self, root: str = ".",
                 scheme: str = "autocontrol") -> None:
        self.root = os.path.realpath(root)
        self.scheme = scheme

    def list(self) -> List[MCPResource]:
        if not os.path.isdir(self.root):
            return []
        out: List[MCPResource] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json"):
                continue
            full = os.path.join(self.root, name)
            if not os.path.isfile(full):
                continue
            out.append(MCPResource(
                uri=f"{self.scheme}://files/{name}",
                name=name,
                description=f"action JSON file in {self.root}",
                mime_type="application/json",
            ))
        return out

    def read(self, uri: str) -> Optional[Dict[str, Any]]:
        prefix = f"{self.scheme}://files/"
        if not uri.startswith(prefix):
            return None
        rel = uri[len(prefix):]
        if "/" in rel or rel.startswith(".") or not rel:
            return None
        path = os.path.realpath(os.path.join(self.root, rel))
        if not path.startswith(self.root + os.sep) and path != self.root:
            return None
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        return {"uri": uri, "mimeType": "application/json", "text": text}


class HistoryProvider(ResourceProvider):
    """Expose recent run-history records under ``autocontrol://history``."""

    URI = "autocontrol://history"

    def list(self) -> List[MCPResource]:
        return [MCPResource(
            uri=self.URI, name="run_history",
            description="Recent script-run history records (last 100).",
            mime_type="application/json",
        )]

    def read(self, uri: str) -> Optional[Dict[str, Any]]:
        if uri != self.URI:
            return None
        from je_auto_control.utils.run_history.history_store import (
            default_history_store,
        )
        rows = default_history_store.list_runs(limit=100)
        data = [{
            "id": row.id, "source_type": row.source_type,
            "source_id": row.source_id, "script_path": row.script_path,
            "started_at": str(row.started_at),
            "finished_at": str(row.finished_at),
            "status": row.status, "error_text": row.error_text,
            "duration_seconds": row.duration_seconds,
        } for row in rows]
        return {
            "uri": uri, "mimeType": "application/json",
            "text": json.dumps(data, ensure_ascii=False, indent=2),
        }


class CommandsProvider(ResourceProvider):
    """Expose the executor command catalogue under ``autocontrol://commands``."""

    URI = "autocontrol://commands"

    def list(self) -> List[MCPResource]:
        return [MCPResource(
            uri=self.URI, name="executor_commands",
            description="Every AC_* command name the executor recognises.",
            mime_type="application/json",
        )]

    def read(self, uri: str) -> Optional[Dict[str, Any]]:
        if uri != self.URI:
            return None
        from je_auto_control.utils.executor.action_executor import executor
        names = sorted(executor.known_commands())
        return {
            "uri": uri, "mimeType": "application/json",
            "text": json.dumps(names, ensure_ascii=False, indent=2),
        }


class ChainProvider(ResourceProvider):
    """Composite that fans out to a tuple of child providers."""

    def __init__(self, providers: List[ResourceProvider]) -> None:
        self.providers = list(providers)

    def list(self) -> List[MCPResource]:
        out: List[MCPResource] = []
        for provider in self.providers:
            out.extend(provider.list())
        return out

    def read(self, uri: str) -> Optional[Dict[str, Any]]:
        for provider in self.providers:
            content = provider.read(uri)
            if content is not None:
                return content
        return None


def default_resource_provider(root: str = ".") -> ResourceProvider:
    """Return the resource provider exposed by the default MCP server."""
    return ChainProvider([
        FileSystemProvider(root=root),
        HistoryProvider(),
        CommandsProvider(),
    ])


__all__ = [
    "ChainProvider", "CommandsProvider", "FileSystemProvider",
    "HistoryProvider", "MCPResource", "ResourceProvider",
    "default_resource_provider",
]
