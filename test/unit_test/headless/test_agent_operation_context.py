"""Operation identity and exact readiness callback ownership, with no SDK, browser or native input."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import context
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.retained_browser_target import RetainedBrowserTarget

PROOF = {"contract": 1, "input_supported": False, "network_retired": True, "context_id": "a" * 32}


def definition():
    return AgentTaskSpec.from_dict({"goal": "Read the retained context", "target": "retained",
        "allowed_tools": ["AC_browser_read"],
        "success_criteria": [{"kind": "actions_complete"}]})


class Pool:
    def __init__(self):
        self.entry = SimpleNamespace(proof=PROOF, channel=self)
        self.released = []

    def borrow(self, _source):
        return self.entry

    def require(self, _source):
        return self.entry

    def release(self, entry):
        self.released.append(entry)

    def discard(self, _task_id):
        pass

    def request(self, operation, _payload, **options):
        options["check"]()
        if operation in {"readonly_capabilities", "bind_browser_reader"}:
            return dict(PROOF)
        assert operation == "observe"
        return {"identity": "original retained context"}


def test_real_retained_borrow_keeps_identical_operation_after_host_readiness():
    spec, pool = definition(), Pool()
    operation = context.TaskOperation(spec, lambda: None, None)
    source = {"id": "original"}
    target = RetainedBrowserTarget(pool, source, spec, lambda: source, context.current_operation)
    with context.operation_scope(operation):
        assert context.ready_with_takeover(target, spec, lambda: None) == (True, "")
        assert context.current_operation() is operation
        assert target.observe() == {"identity": "original retained context"}
        with context.operation_scope(context.TaskOperation(spec, lambda: None, None)):
            with pytest.raises(AgentTaskError, match="current scoped borrow"):
                target.observe()
    assert pool.released == [pool.entry]


def test_native_readiness_captures_exact_host_callback_without_changing_operation(monkeypatch):
    spec, calls = definition(), []
    parent = context.TaskOperation(spec, lambda: None, None, lambda: calls.append("ambient"))
    target = NativeDesktopTarget(argv=("unused",))

    def request(*_args, **_options):
        assert context.current_operation() is parent
        return {"ready": True}

    monkeypatch.setattr(target, "_request", request)
    with context.operation_scope(parent):
        assert context.ready_with_takeover(target, spec, lambda: calls.append("bound")) == (True, "")
        captured = target._takeover
        assert context.current_takeover() is parent.takeover
    captured()
    assert calls == ["bound"]
    assert context.current_operation() is None and context.current_takeover() is None


def test_nested_operation_cannot_borrow_outer_readiness_callback():
    spec, calls = definition(), []
    parent = context.TaskOperation(spec, lambda: None, None, lambda: calls.append("parent"))
    child = context.TaskOperation(spec, lambda: None, None, lambda: calls.append("child"))

    class Target:
        def ready(self, _spec):
            assert context.current_operation() is parent
            outer = context.current_takeover()
            with context.operation_scope(child):
                assert context.current_takeover() is child.takeover
            assert context.current_takeover() is outer
            outer()
            return True, ""

    with context.operation_scope(parent):
        assert context.ready_with_takeover(Target(), spec, lambda: calls.append("bound")) == (True, "")
        assert context.current_takeover() is parent.takeover
    assert calls == ["bound"]


def test_failed_readiness_restores_exact_scope_and_default_callback():
    spec = definition()
    parent = context.TaskOperation(spec, lambda: None, None, lambda: None)

    class Target:
        def ready(self, _spec):
            assert context.current_operation() is parent
            raise AgentTaskError("owned failure")

    with context.operation_scope(parent):
        with pytest.raises(AgentTaskError, match="owned failure"):
            context.ready_with_takeover(Target(), spec, lambda: None)
        assert context.current_operation() is parent and context.current_takeover() is parent.takeover
    assert context.current_takeover() is None


def test_native_takeover_retains_optional_sqlite_error_diagnostics():
    from je_auto_control.utils.agent_runtime.native_control import NativeControl
    from je_auto_control.utils.sqlite_support import SQLITE_ERRORS, require_sqlite3
    if not SQLITE_ERRORS:
        pytest.skip("SQLite error branch requires the optional extension")

    def takeover():
        raise require_sqlite3().OperationalError("owned storage failure")

    control = NativeControl(takeover)
    control._run()
    assert control.status()["cleanup_error"] == "OperationalError"
