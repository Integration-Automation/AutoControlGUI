"""Permanently read-only owned helper: observation never upgrades to native input or task execution."""
from __future__ import annotations

import json
import sys
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
from je_auto_control.utils.agent_runtime.parent_watch import start_parent_watch
from je_auto_control.utils.executor.dispatch import command_guard
from je_auto_control.wrapper._input_observer import input_observer


# pylint: disable-next=too-few-public-methods  # reason: one inherited RPC loop with permanently restricted dispatch
class ReadOnlyWorker(NativeWorker):
    """Keep the read-only boundary in the helper, independently of the host's restricted view."""

    def __init__(self, source: Any, sink: Any, *, target: Any = None) -> None:
        super().__init__(source, sink, target=target)
        self._configuration: str | None = None

    def _dispatch(self, operation: str, payload: dict) -> Any:
        if operation == "readonly_capabilities" and payload == {}:
            return {"contract": 1, "input_supported": False}
        if operation not in {"bootstrap", "configure", "observe", "verify_browser", "cleanup"}:
            raise AgentTaskError("read-only helper refuses executable operations")
        return super()._dispatch(operation, payload)

    def _configure_scope(self, payload: dict) -> None:
        if set(payload) - {"spec", "owner", "profile"}:
            raise AgentTaskError("read-only helper cannot replace its configured authority")
        configuration = json.dumps(payload, sort_keys=True, allow_nan=False)
        if self._spec is not None:
            if configuration != self._configuration:
                raise AgentTaskError("read-only helper cannot replace its configured authority")
            return
        super()._configure_scope(payload)
        self._configuration = configuration

    def _operation(self, operation: str, payload: dict) -> Any:
        if operation == "configure":
            if self._profile_kind == "browser":
                return {"ready": False, "reason": "fresh browser startup is not a read-only observation"}
            ready, reason = self._target.ready(self._spec)
            return {"ready": ready, "reason": reason}
        return super()._operation(operation, payload)

    def _guard(self, _policy: Any, name: str, _arguments: Any) -> None:
        raise AgentTaskError(f"read-only observation cannot dispatch {name!r}")

    def _input(self, _event: dict) -> None:
        raise AgentTaskError("read-only helper cannot acknowledge native input")

    def _release_owned(self, payload: dict) -> dict:
        if payload != {"keys": [], "buttons": []}:
            raise AgentTaskError("read-only helper cannot inject cleanup input")
        with command_guard(lambda name, arguments: self._guard(None, name, arguments)), input_observer(self._input):
            self._target.cleanup()
        return {"cleaned": True}


def main() -> None:
    """Launch only as an explicit host-owned read-only child, with parent retirement monitoring."""
    start_parent_watch()
    ReadOnlyWorker(sys.stdin.buffer, sys.stdout.buffer).run()


if __name__ == "__main__":
    main()
