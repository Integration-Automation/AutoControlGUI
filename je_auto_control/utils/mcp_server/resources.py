"""MCP resource providers for AutoControl.

Resources let an MCP client browse data the server has to offer
without invoking a tool — typical use cases here are listing the
JSON action library on disk, fetching the run-history snapshot, and
inspecting which executor commands the model can call. The provider
abstraction lets callers compose custom sources without touching the
JSON-RPC layer.
"""
import base64
import io
import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


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

    def set_workspace_root(self, root: str) -> None:
        """Hook for MCP roots. Default: no-op. FS-backed providers override."""
        del root

    def subscribe(self, uri: str,
                  on_update: Callable[[], None]) -> Optional[Any]:
        """Optional hook: start emitting ``on_update`` calls until unsubscribed.

        Return a non-``None`` handle when this provider owns ``uri`` and
        accepted the subscription. The default implementation returns
        ``None`` (not subscribable).
        """
        del uri, on_update
        return None

    def unsubscribe(self, uri: str, handle: Any) -> None:
        """Cancel a previous :meth:`subscribe` handle."""
        del uri, handle


class FileSystemProvider(ResourceProvider):
    """Expose ``*.json`` action files in ``root`` under ``<scheme>://files/<name>``."""

    def __init__(self, root: str = ".",
                 scheme: str = "autocontrol") -> None:
        self.root = os.path.realpath(root)
        self.scheme = scheme

    def set_workspace_root(self, root: str) -> None:
        """Re-target the provider at a new directory (e.g. via MCP roots)."""
        self.root = os.path.realpath(os.fspath(root))

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

    def set_workspace_root(self, root: str) -> None:
        """Forward the root to every child provider."""
        for provider in self.providers:
            provider.set_workspace_root(root)

    def subscribe(self, uri: str,
                  on_update: Callable[[], None]) -> Optional[Any]:
        for provider in self.providers:
            handle = provider.subscribe(uri, on_update)
            if handle is not None:
                return (provider, handle)
        return None

    def unsubscribe(self, uri: str, handle: Any) -> None:
        if not isinstance(handle, tuple) or len(handle) != 2:
            return
        provider, child_handle = handle
        provider.unsubscribe(uri, child_handle)


class LiveScreenProvider(ResourceProvider):
    """Live screen feed at ``autocontrol://screen/live``.

    ``read`` always grabs a fresh PNG (base64-encoded). Subscribers
    receive ``on_update`` calls every ``poll_seconds`` so they can
    re-fetch the resource and surface live state to the model.
    """

    URI = "autocontrol://screen/live"

    def __init__(self, poll_seconds: float = 1.0) -> None:
        self._poll_seconds = max(0.1, float(poll_seconds))
        self._lock = threading.Lock()
        self._subscribers: Dict[int, Callable[[], None]] = {}
        self._next_handle = 1
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def list(self) -> List[MCPResource]:
        return [MCPResource(
            uri=self.URI, name="screen_live",
            description=("Current screen as base64 PNG. Subscribe to be "
                          "notified when it should be re-fetched."),
            mime_type="image/png",
        )]

    def read(self, uri: str) -> Optional[Dict[str, Any]]:
        if uri != self.URI:
            return None
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        image = pil_screenshot()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return {"uri": uri, "mimeType": "image/png", "blob": encoded}

    def subscribe(self, uri: str,
                  on_update: Callable[[], None]) -> Optional[Any]:
        if uri != self.URI:
            return None
        with self._lock:
            handle = self._next_handle
            self._next_handle += 1
            self._subscribers[handle] = on_update
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._broadcast_loop, daemon=True,
                    name="MCPLiveScreen",
                )
                self._thread.start()
        return handle

    def unsubscribe(self, uri: str, handle: Any) -> None:
        if uri != self.URI:
            return
        with self._lock:
            self._subscribers.pop(int(handle), None)
            if not self._subscribers:
                self._stop.set()
                self._thread = None

    def _broadcast_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                callbacks = list(self._subscribers.values())
            for callback in callbacks:
                try:
                    callback()
                except (OSError, RuntimeError, ValueError):
                    pass
            self._stop.wait(self._poll_seconds)


def default_resource_provider(root: str = ".") -> ResourceProvider:
    """Return the resource provider exposed by the default MCP server."""
    return ChainProvider([
        FileSystemProvider(root=root),
        HistoryProvider(),
        CommandsProvider(),
        LiveScreenProvider(),
    ])


__all__ = [
    "ChainProvider", "CommandsProvider", "FileSystemProvider",
    "HistoryProvider", "LiveScreenProvider", "MCPResource",
    "ResourceProvider", "default_resource_provider",
]
