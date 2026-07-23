"""Background watcher that hot-reloads plugin tools when files change.

Polls a plugin directory at a configurable interval, comparing each
``*.py`` file's mtime to its previous reading. When a file changes
(created, modified, or removed) the watcher reloads it via the
plugin loader and registers / unregisters MCP tools so the model
sees the updated catalogue without a server restart.
"""
import os
import threading
from typing import Any, Dict, List, Optional, Set

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.tools.plugin_tools import (
    make_plugin_tool,
)


class PluginWatcher:
    """Polling watcher that keeps an MCPServer's registry in sync with disk."""

    def __init__(self, server: Any, directory: str,
                 poll_seconds: float = 2.0) -> None:
        self._server = server
        self._directory = os.path.realpath(os.fspath(directory))
        self._poll_seconds = max(0.2, float(poll_seconds))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # path → (mtime, [tool_names])
        self._known: Dict[str, tuple] = {}

    @property
    def directory(self) -> str:
        return self._directory

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not os.path.isdir(self._directory):
            raise NotADirectoryError(
                f"plugin directory not found: {self._directory}"
            )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="MCPPluginWatcher",
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def poll_once(self) -> None:
        """Run one scan-and-sync iteration. Public for tests."""
        seen: Set[str] = set()
        for entry in sorted(os.listdir(self._directory)):
            if not entry.endswith(".py") or entry.startswith("_"):
                continue
            full = os.path.join(self._directory, entry)
            if not os.path.isfile(full):
                continue
            seen.add(full)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            previous = self._known.get(full)
            if previous is None or previous[0] != mtime:
                self._reload_file(full, mtime)
        for stale in set(self._known) - seen:
            self._unregister_file(stale)

    # --- internals ----------------------------------------------------------

    def _run(self) -> None:
        autocontrol_logger.info(
            "plugin watcher started: %s (every %ss)",
            self._directory, self._poll_seconds,
        )
        while not self._stop.is_set():
            try:
                self.poll_once()
            except OSError as error:
                autocontrol_logger.warning(
                    "plugin watcher poll failed: %r", error,
                )
            self._stop.wait(self._poll_seconds)
        autocontrol_logger.info("plugin watcher stopped")

    def _reload_file(self, path: str, mtime: float) -> None:
        previous = self._known.get(path)
        tools = self._build_tools(path, previous, mtime)
        if tools is None:
            return
        # Build succeeded — only now swap the live registry. Doing the
        # unregister *after* a successful build means a broken edit leaves the
        # file's existing tools in place instead of vanishing them.
        if previous is not None:
            for tool_name in previous[1]:
                self._server.unregister_tool(tool_name)
        registered: List[str] = []
        for tool in tools:
            self._server.register_tool(tool)
            registered.append(tool.name)
        self._known[path] = (mtime, registered)
        autocontrol_logger.info(
            "plugin %s reloaded → %d tools", os.path.basename(path),
            len(registered),
        )

    def _build_tools(self, path: str, previous: Optional[tuple],
                     mtime: float) -> Optional[List[Any]]:
        """Load ``path`` and build its tools, or ``None`` on any failure.

        Plugin files run arbitrary user code, so loading or tool construction
        may raise anything (NameError, ValueError, …). We catch broadly to keep
        the watcher thread alive; on failure the previously-registered tools
        are retained and the mtime is recorded so we don't rebuild every poll.
        """
        from je_auto_control.utils.plugin_loader.plugin_loader import (
            load_plugin_file,
        )
        try:
            commands = load_plugin_file(path)
            return [make_plugin_tool(raw_name, handler)
                    for raw_name, handler in commands.items()]
        except Exception as error:  # pylint: disable=broad-exception-caught  # reason: plugin code is untrusted and may raise anything
            autocontrol_logger.warning(
                "plugin %s reload failed, keeping previous tools: %r",
                path, error,
            )
            self._known[path] = (mtime, previous[1] if previous else [])
            return None

    def _unregister_file(self, path: str) -> None:
        previous = self._known.pop(path, None)
        if previous is None:
            return
        for tool_name in previous[1]:
            self._server.unregister_tool(tool_name)
        autocontrol_logger.info(
            "plugin %s removed → %d tools dropped",
            os.path.basename(path), len(previous[1]),
        )


__all__ = ["PluginWatcher"]
