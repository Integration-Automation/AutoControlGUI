"""Private native helper entry point; stdout is a bounded owner-only JSON protocol."""
from __future__ import annotations

import json
import sys
import threading
from contextlib import ExitStack
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.browser_retirement import refuse_browser_tool
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, durable_payload
from je_auto_control.utils.agent_runtime.targets import DesktopTarget
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.dispatch import command_guard
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.script_vars.execution import execution_scope
from je_auto_control.wrapper._input_observer import input_observer
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.presence_frames import presence_body
from je_auto_control.utils.agent_runtime.presence_reader import PresenceReader

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
        self._presence_binding: dict | None = None
        self._notice_stop = threading.Event()
        self._notice_thread: threading.Thread | None = None

    @property
    def _browser_readonly(self) -> bool:
        return isinstance(self._target, BrowserTarget) and self._target.input_retired

    def _reply(self, payload: dict) -> None:
        packet = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(packet) > _LIMIT:
            raise AgentTaskError("native response is too large")
        with self._sink_lock:
            self._sink.write(packet)
            self._sink.flush()

    def _physical_takeover(self) -> None:
        while not self._notice_stop.is_set():
            if self._control_event.wait(0.05):
                self._reply({"control": "physical_input"})
                return

    def _validate_input(self, event: dict) -> None:
        """Recheck live permission; cleanup may acknowledge owned release boundaries only."""
        if self._cleanup:
            if event.get("kind") not in {"key_release", "key_released", "mouse_release", "mouse_released"}:
                raise AgentTaskError("native cleanup permits owned release events only")
            return
        self._check_activity()
        self._target.validate_input(event)

    def _input(self, event: dict) -> None:
        if self._browser_readonly:
            raise AgentTaskError("read-only browser cannot acknowledge native input")
        self._validate_input(event)
        if not self._cleanup and event.get("move_before_press"):
            if event.get("kind") != "mouse_press":
                raise AgentTaskError("only a mouse press may request pointer preparation")
            self._target.prepare_input(event)
            self._validate_input(event)
        self._reply({"id": self._request_id, "event": event})
        line = self._source.readline(_LIMIT + 1)
        if not line or len(line) > _LIMIT:
            raise AgentTaskError("native input was not acknowledged by its owner")
        acknowledgement = json.loads(line)
        if (not isinstance(acknowledgement, dict) or set(acknowledgement) != {"ack"}
                or acknowledgement["ack"] is not True):
            raise AgentTaskError("native input was not acknowledged by its owner")
        self._validate_input(event)

    def run(self) -> None:
        """Serve one serial stream; native exceptions remain confined to this owned process."""
        try:
            self._serve()
        finally:
            self.close()

    def _serve(self) -> None:
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
        if self._browser_readonly:
            with input_observer(self._input):
                return self._dispatch_browser_readonly(operation, payload)
        if operation == "retire_browser":
            return self._retire_browser(payload)
        if operation == "bootstrap":
            return self._bootstrap()
        if operation == "cleanup":
            return self._release_owned(payload)
        if operation == "probe_browser":
            return self._probe_browser(payload)
        if operation == "configure":
            self._configure_scope(payload)
        return self._scoped_operation(operation, payload)

    def _bootstrap(self) -> dict:
        """Advertise optional retirement only on the built-in original configured browser worker."""
        result = {"protocol": 1}
        # pylint: disable-next=unidiomatic-typecheck  # reason: read-only/custom worker subclasses cannot claim this API
        if type(self) is NativeWorker and self._profile_kind == "browser" and isinstance(self._target, BrowserTarget):
            result["browser_readonly"] = 1
        return result

    def _scoped_operation(self, operation: str, payload: dict) -> Any:
        if self._spec is None:
            raise AgentTaskError("native worker must be configured by its owner")
        definition = self._target.readonly_spec if self._browser_readonly else self._spec
        with ExitStack() as stack:
            authority = DeferredAuthorization(self._owner).scope() if self._browser_readonly else (
                authorization_scope(self._owner))
            stack.enter_context(authority)
            policy = TaskPolicy(definition)
            stack.enter_context(command_guard(lambda name, arguments: self._guard(policy, name, arguments)))
            stack.enter_context(execution_scope(dict(definition.inputs)))
            stack.enter_context(input_observer(self._input))
            stack.enter_context(operation_scope(TaskOperation(definition, self._check_activity, self._owner)))
            return self._operation(operation, payload)

    def _retire_browser(self, payload: dict) -> dict:
        if payload != {} or self._profile_kind != "browser" or self._spec is None:
            raise AgentTaskError("browser retirement requires the configured original scope")
        with command_guard(refuse_browser_tool), input_observer(self._input):
            if not self._target.can_freeze_readonly:
                return {"supported": False}
            return self._target.freeze_readonly()

    def _dispatch_browser_readonly(self, operation: str, payload: dict) -> Any:
        if operation == "cleanup":
            return self._cleanup_browser_readonly(payload)
        _readonly_browser_payload(operation, payload)
        with command_guard(refuse_browser_tool):
            proof = self._target.readonly_capabilities()
            if operation in {"readonly_capabilities", "retire_browser"}:
                return proof
            if operation == "bind_browser_reader":
                return self._target.bind_readonly(payload["spec"], validate=TaskPolicy)
        return self._scoped_operation(operation, payload)

    def _cleanup_browser_readonly(self, payload: dict) -> dict:
        if payload != {"keys": [], "buttons": []}:
            raise AgentTaskError("read-only browser cleanup cannot inject input")
        with command_guard(refuse_browser_tool), input_observer(self._input):
            self._target.cleanup()
        return {"cleaned": True}

    def _probe_browser(self, payload: dict) -> dict:
        if self._spec is not None or not isinstance(payload, dict) or set(payload) != {"transfer"}:
            raise AgentTaskError("dependency probing requires an unconfigured owned helper")
        # pylint: disable-next=import-outside-toplevel  # reason: only an explicit unconfigured probe loads this seam
        from je_auto_control.utils.agent_runtime.browser_environment import inspect_browser_dependencies
        return inspect_browser_dependencies(payload["transfer"])

    def _configure_scope(self, payload: dict) -> None:
        spec = AgentTaskSpec.from_dict(payload["spec"])
        owner = AuthorizationContext(**payload["owner"]) if payload.get("owner") else None
        self._check_presence_pin(spec, owner, payload)
        self._spec, self._owner = spec, owner
        self._configure_profile(payload)
        if not self._custom_target and (self._spec.target == "local-files" or self._profile_kind == "files"):
            from je_auto_control.utils.agent_runtime.file_target import FileTarget
            self._target = FileTarget()
        if not self._custom_target and self._profile_kind == "browser":
            if not isinstance(self._target, BrowserTarget):
                self._target = BrowserTarget()
        self._configure_presence(payload)

    def _check_presence_pin(self, spec: AgentTaskSpec, owner: AuthorizationContext | None, payload: dict) -> None:
        if self._presence_binding is not None and (spec != self._spec or owner != self._owner
                                                  or payload.get('presence') != self._presence_binding):
            raise AgentTaskError('configured desktop presence cannot change capability or owner scope')

    def _configure_presence(self, payload: dict) -> None:
        if self._requires_presence():
            binding = payload.get('presence')
            if not isinstance(binding, dict):
                raise AgentTaskError('standard desktop worker requires a host presence binding')
            self._presence_binding = presence_body('check', binding)

    def _requires_presence(self) -> bool:
        return (not self._custom_target and self._spec is not None and self._spec.target != 'local-files'
                and self._profile_kind not in {'files', 'browser'})

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
        if self._browser_readonly and name != "AC_browser_read":
            raise AgentTaskError("read-only browser cannot dispatch tools")
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
        if not self._requires_presence():
            return
        if self._activity is None:
            if self._presence_binding is None:
                raise AgentTaskError('standard desktop worker has no host presence binding')
            self._activity = PresenceReader(self._presence_binding, self._control_event.set)
            self._notice_thread = threading.Thread(target=self._physical_takeover,
                                                   name='AgentPresenceNotice', daemon=True)
            try:
                self._notice_thread.start()
            except (RuntimeError, OSError) as error:
                self.close()
                raise AgentTaskError('physical presence notice thread could not start') from error
        self._activity.ready()

    def close(self) -> None:
        """Retire only this worker's reader/notice; input release remains a separate owner ACK path."""
        if self._presence_binding is None:
            return
        self._notice_stop.set()
        if self._activity is not None:
            self._activity.close()
        if self._notice_thread is not None and self._notice_thread.ident is not None:
            self._notice_thread.join(timeout=0.25)
            if self._notice_thread.is_alive():
                raise AgentTaskError('physical presence notice has not retired; owned helper must retire')

    @staticmethod
    def _release_key(key: dict) -> None:
        from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key, _release_unicode_unit
        if key.get('unicode'):
            _release_unicode_unit(key['keycode'])
        else:
            release_keyboard_key(key['keycode'], key['is_shift'], skip_record=True)

    def _release_owned(self, payload: dict) -> dict:
        from je_auto_control.wrapper.auto_control_mouse import release_mouse
        if set(payload) != {"keys", "buttons"}:
            raise AgentTaskError("cleanup payload is invalid")
        failures = []
        self._cleanup = True
        try:
            with input_observer(self._input):
                for key in reversed(payload["keys"]):
                    try:
                        self._release_key(key)
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
        self.close()
        return {"cleaned": True}


def _readonly_browser_payload(operation: str, payload: Any) -> None:
    fields = {"observe": set(), "verify_browser": {"clause"}, "bind_browser_reader": {"spec"},
              "readonly_capabilities": set(), "retire_browser": set()}
    if operation not in fields or not isinstance(payload, dict) or set(payload) != fields[operation]:
        raise AgentTaskError("read-only browser refuses executable or reconfiguration operations")


def main() -> None:
    """Run only when explicitly launched by a host-owned NativeDesktopTarget."""
    from je_auto_control.utils.agent_runtime.parent_watch import start_parent_watch
    start_parent_watch()
    NativeWorker(sys.stdin.buffer, sys.stdout.buffer).run()


if __name__ == "__main__":
    main()
