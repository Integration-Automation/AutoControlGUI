"""Private native helper entry point; stdout is a bounded owner-only JSON protocol."""
from __future__ import annotations

import json
import sys
import threading
from contextlib import ExitStack
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, durable_payload
from je_auto_control.utils.agent_runtime.targets import DesktopTarget
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.dispatch import command_guard
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.script_vars.execution import execution_scope
from je_auto_control.wrapper._input_observer import input_observer
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope

_LIMIT = 1_100_000


class NativeWorker:
    """Only the owning process can configure this helper or acknowledge its input."""

    def __init__(self, source: Any, sink: Any, *, target: Any = None) -> None:
        self._source, self._sink = source, sink
        self._target: Any = target if target is not None else DesktopTarget()
        self._custom_target = target is not None
        self._profile_kind = ""
        self._spec: AgentTaskSpec | None = None
        self._owner: AuthorizationContext | None = None
        self._request_id = ""
        self._cleanup = False
        self._activity: Any = None
        self._control_event = threading.Event()
        self._sink_lock = threading.Lock()

    def _reply(self, payload: dict) -> None:
        packet = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(packet) > _LIMIT:
            raise AgentTaskError("native response is too large")
        with self._sink_lock:
            self._sink.write(packet)
            self._sink.flush()

    def _physical_takeover(self) -> None:
        self._control_event.wait()
        self._reply({"control": "physical_input"})

    def _input(self, event: dict) -> None:
        if not self._cleanup:
            if self._activity is not None:
                self._activity.check()
            self._target.validate_input(event)
            if event.get("move_before_press"):
                if event.get("kind") != "mouse_press":
                    raise AgentTaskError("only a mouse press may request pointer preparation")
                self._target.prepare_input(event)
                self._target.validate_input(event)
        self._reply({"id": self._request_id, "event": event})
        line = self._source.readline(_LIMIT + 1)
        if not line or len(line) > _LIMIT or json.loads(line) != {"ack": True}:
            raise AgentTaskError("native input was not acknowledged by its owner")

    def run(self) -> None:
        """Serve one serial stream; native exceptions remain confined to this owned process."""
        while True:
            line = self._source.readline(_LIMIT + 1)
            if not line:
                return
            if len(line) > _LIMIT or not line.endswith(b"\n"):
                return
            request = json.loads(line)
            self._request_id = str(request.get("id", ""))
            try:
                result = self._dispatch(request["operation"], request["payload"])
                self._reply({"id": self._request_id, "result": durable_payload(result)})
            except (AutoControlException, OSError, RuntimeError, TypeError, ValueError, LookupError) as error:
                self._reply(durable_payload({"id": self._request_id, "error": f"{type(error).__name__}: {error}",
                                             "error_type": type(error).__name__}))

    def _dispatch(self, operation: str, payload: dict) -> Any:
        if operation == "bootstrap":
            return {"protocol": 1}
        if operation == "cleanup":
            return self._release_owned(payload)
        if operation == "configure":
            self._configure_scope(payload)
        if self._spec is None:
            raise AgentTaskError("native worker must be configured by its owner")
        with ExitStack() as stack:
            stack.enter_context(authorization_scope(self._owner))
            policy = TaskPolicy(self._spec)
            stack.enter_context(command_guard(lambda name, arguments: self._guard(policy, name, arguments)))
            stack.enter_context(execution_scope(dict(self._spec.inputs)))
            stack.enter_context(input_observer(self._input))
            stack.enter_context(operation_scope(TaskOperation(self._spec, self._check_activity, self._owner)))
            return self._operation(operation, payload)

    def _configure_scope(self, payload: dict) -> None:
        self._spec = AgentTaskSpec.from_dict(payload["spec"])
        self._owner = AuthorizationContext(**payload["owner"]) if payload.get("owner") else None
        self._configure_profile(payload)
        if not self._custom_target and (self._spec.target == "local-files" or self._profile_kind == "files"):
            from je_auto_control.utils.agent_runtime.file_target import FileTarget
            self._target = FileTarget()
        if not self._custom_target and self._profile_kind == "browser":
            from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
            if not isinstance(self._target, BrowserTarget):
                self._target = BrowserTarget()

    def _configure_profile(self, payload: dict) -> None:
        if "profile" not in payload:
            return
        from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile, check_host_platform
        profile = AgentTargetProfile.from_dict(payload["profile"])
        if self._spec is None or self._spec.target != profile.name:
            raise AgentTaskError("native target profile does not match its managed resource")
        profile.check(self._spec)
        check_host_platform(profile)
        pin = {"name": profile.name, "digest": profile.digest}
        if self._spec.options.get("target_profile") != pin:
            raise AgentTaskError("native target profile pin is invalid")
        self._profile_kind = profile.kind

    def _check_activity(self) -> None:
        if self._activity is not None:
            self._activity.check()

    def _guard(self, policy: TaskPolicy, name: str, arguments: Any) -> None:
        self._check_activity()
        policy.check(name, arguments)

    def _operation(self, operation: str, payload: dict) -> Any:
        if operation == "configure":
            if self._spec is None:
                raise AgentTaskError("native worker has no configured scope")
            self._ready_activity()
            ready, reason = self._target.ready(self._spec)
            return {"ready": ready, "reason": reason}
        if operation == "observe":
            return self._target.observe()
        if operation == "perform":
            return self._target.perform(payload["tool"], payload["arguments"])
        if operation == "verify_browser":
            if self._profile_kind != "browser" and not self._custom_target:
                raise AgentTaskError("browser verification is unavailable on this target")
            return self._target.verify_browser(payload["clause"])
        raise AgentTaskError("unknown native worker operation")

    def _ready_activity(self) -> None:
        if self._custom_target or self._spec is None or self._profile_kind in {"files", "browser"}:
            return
        if self._spec.target == "local-files":
            return
        if self._activity is None:
            from je_auto_control.utils.agent_runtime.activity import desktop_activity_gate
            self._activity = desktop_activity_gate(self._control_event.set)
            threading.Thread(target=self._physical_takeover, name="AgentPresenceNotice", daemon=True).start()
        self._activity.ready()

    def _release_owned(self, payload: dict) -> dict:
        from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key, _release_unicode_unit
        from je_auto_control.wrapper.auto_control_mouse import release_mouse
        if set(payload) != {"keys", "buttons"}:
            raise AgentTaskError("cleanup payload is invalid")
        failures = []
        self._cleanup = True
        try:
            with input_observer(self._input):
                for key in reversed(payload["keys"]):
                    try:
                        if key.get("unicode"):
                            _release_unicode_unit(key["keycode"])
                        else:
                            release_keyboard_key(key["keycode"], key["is_shift"], skip_record=True)
                    except AutoControlException as error:
                        failures.append(type(error).__name__)
                for button in reversed(payload["buttons"]):
                    try:
                        release_mouse(button["keycode"], button["x"], button["y"])
                    except AutoControlException as error:
                        failures.append(type(error).__name__)
        finally:
            self._cleanup = False
        if failures:
            raise AgentTaskError("owned native input cleanup is incomplete")
        self._target.cleanup()
        return {"cleaned": True}


def main() -> None:
    """Run only when explicitly launched by a host-owned NativeDesktopTarget."""
    from je_auto_control.utils.agent_runtime.parent_watch import start_parent_watch
    start_parent_watch()
    NativeWorker(sys.stdin.buffer, sys.stdout.buffer).run()


if __name__ == "__main__":
    main()
