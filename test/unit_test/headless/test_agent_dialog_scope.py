"""Managed dialog and UIA ownership gates use fake handles and accessibility trees."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError, AgentTaskSpec


@pytest.mark.parametrize("name", ["Don't save", "Discard changes", "未儲存", "保存しない"])
def test_unsaved_modal_requires_human_review_even_with_a_known_file_title(monkeypatch, name):
    from je_auto_control.utils.agent_runtime import dialog_scope
    monkeypatch.setattr(dialog_scope, "_window_metadata", lambda _hwnd: {"modal": True, "class_name": "#32770"})
    with pytest.raises(AgentTaskError, match="unsaved"):
        dialog_scope.check_review(10, "Save As", [SimpleNamespace(name=name)], workspace=False)


def test_unknown_modal_is_never_treated_as_a_file_picker(monkeypatch):
    from je_auto_control.utils.agent_runtime import dialog_scope
    monkeypatch.setattr(dialog_scope, "_window_metadata", lambda _hwnd: {"modal": True, "class_name": "Custom"})
    with pytest.raises(AgentTaskError, match="dialog"):
        dialog_scope.check_review(10, "Confirm", [], workspace=False)


def test_known_file_dialog_is_observable_and_dirty_workspace_title_is_paused(monkeypatch):
    from je_auto_control.utils.agent_runtime import dialog_scope
    monkeypatch.setattr(dialog_scope, "_window_metadata", lambda _hwnd: {"modal": True, "class_name": "#32770"})
    dialog_scope.check_review(10, "Open", [], workspace=False)
    monkeypatch.setattr(dialog_scope, "_window_metadata", lambda _hwnd: {"modal": False, "class_name": "Editor"})
    with pytest.raises(AgentTaskError, match="unsaved"):
        dialog_scope.check_review(10, "*report.txt", [], workspace=True)
    dialog_scope.check_review(10, "*report.txt", [], workspace=False)


def test_workspace_bootstrap_does_not_hide_human_review(monkeypatch):
    from je_auto_control.utils.agent_runtime import dialog_scope
    from je_auto_control.utils.agent_runtime.targets import DesktopTarget
    target = DesktopTarget()
    target._spec = AgentTaskSpec.from_dict({"goal": "workspace", "apps": ["editor"],
        "allowed_tools": ["AC_focus_window"], "actions": [{"tool": "AC_focus_window"}],
        "success_criteria": [{"kind": "actions_complete"}]})

    def refuse():
        raise dialog_scope.AgentHumanReview("unsaved content needs review")

    monkeypatch.setattr(target, "_check_foreground", refuse)
    with pytest.raises(dialog_scope.AgentHumanReview):
        target.observe()


def test_uia_lookup_cannot_operate_another_window_of_the_same_process(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_scope
    from je_auto_control.utils.accessibility import backends
    raw = SimpleNamespace(CurrentProcessId=7, CurrentNativeWindowHandle=22)
    original = lambda **_kwargs: raw
    backend = SimpleNamespace(_find_raw=original, _ensure_automation=lambda: SimpleNamespace(ControlViewWalker=None))
    monkeypatch.setattr(backends, "get_backend", lambda: backend)
    monkeypatch.setattr(native_scope.sys, "platform", "win32")
    monkeypatch.setattr(native_scope, "_hit_library", lambda: SimpleNamespace(
        GetAncestor=lambda _hwnd, _kind: 22, GetForegroundWindow=lambda: 11))
    with native_scope.control_owner_scope(7, 11):
        with pytest.raises(AgentTaskError, match="window"):
            backend._find_raw(name="Save")
    assert backend._find_raw is original


def test_uia_lookup_walks_to_the_actual_owned_hwnd_without_widening_to_its_owner(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_scope
    from je_auto_control.utils.accessibility import backends
    child = SimpleNamespace(CurrentProcessId=7, CurrentNativeWindowHandle=0)
    parent = SimpleNamespace(CurrentProcessId=7, CurrentNativeWindowHandle=12)
    walker = SimpleNamespace(GetParentElement=lambda raw: parent if raw is child else None)
    backend = SimpleNamespace(_find_raw=lambda **_kwargs: child,
                              _ensure_automation=lambda: SimpleNamespace(ControlViewWalker=walker))
    monkeypatch.setattr(backends, "get_backend", lambda: backend)
    monkeypatch.setattr(native_scope.sys, "platform", "win32")
    monkeypatch.setattr(native_scope, "_hit_library", lambda: SimpleNamespace(
        GetAncestor=lambda hwnd, kind: 11 if (hwnd, kind) == (12, 2) else 0, GetForegroundWindow=lambda: 11))
    with native_scope.control_owner_scope(7, 11):
        assert backend._find_raw(name="Save") is child


@pytest.mark.parametrize("broken_provider", [True, False])
def test_uia_provider_failure_or_focus_change_fails_closed_and_restores_lookup(monkeypatch, broken_provider):
    from je_auto_control.utils.agent_runtime import native_scope
    from je_auto_control.utils.accessibility import backends
    raw = SimpleNamespace(CurrentProcessId=7)
    if not broken_provider:
        raw.CurrentNativeWindowHandle = 11
    original = lambda **_kwargs: raw
    backend = SimpleNamespace(_find_raw=original, _ensure_automation=lambda: SimpleNamespace(ControlViewWalker=None))
    monkeypatch.setattr(backends, "get_backend", lambda: backend)
    monkeypatch.setattr(native_scope.sys, "platform", "win32")
    monkeypatch.setattr(native_scope, "_hit_library", lambda: SimpleNamespace(
        GetAncestor=lambda _hwnd, _kind: 11, GetForegroundWindow=lambda: 22))
    with native_scope.control_owner_scope(7, 11):
        with pytest.raises(AgentTaskError, match="ownership|focus"):
            backend._find_raw(name="Save")
    assert backend._find_raw is original


def test_external_observation_review_releases_input_and_requires_resume(tmp_path):
    from je_auto_control.utils.agent_runtime import AgentRuntime, AgentHumanReview
    cleanup = []

    def observe():
        raise AgentHumanReview("unsaved content")

    target = SimpleNamespace(ready=lambda _spec: (True, ""), observe=observe, cleanup=lambda: cleanup.append(True))
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    try:
        task = runtime.submit({"goal": "review", "target": "fixture", "allowed_tools": ["AC_click_mouse"],
                               "success_criteria": [{"kind": "result_equals", "key": "saved", "value": True}]})
        with pytest.raises(AgentHumanReview):
            runtime.observe(task.task_id)
        assert runtime.get(task.task_id).state == "waiting_user"
        assert not runtime._leases and cleanup
        assert runtime.store.actions(task.task_id) == []
        runtime.resume(task.task_id)
        assert runtime.get(task.task_id).state == "queued"
    finally:
        runtime.close()


def test_file_dialog_rejects_foreign_and_duplicate_matches_before_focus(monkeypatch):
    from je_auto_control.utils.agent_runtime import file_dialog_scope
    from je_auto_control.wrapper import window_backends
    focus = []
    target = SimpleNamespace(_action_identity=(11, 7))
    policy = SimpleNamespace(spec=SimpleNamespace(budget=SimpleNamespace(action_seconds=1)))
    monkeypatch.setattr(file_dialog_scope, "task_policy", lambda: policy)
    backend = SimpleNamespace(list_windows=lambda: [(20, "Open")], window_process_id=lambda _hwnd: 99,
                              bring_to_front=lambda hwnd: focus.append(hwnd))
    monkeypatch.setattr(window_backends, "get_backend", lambda: backend)
    driver = file_dialog_scope._ScopedDriver(target, 11, 7)
    with pytest.raises(AgentTaskError, match="another process"):
        driver.wait_window("Open", 1)
    backend.list_windows = lambda: [(20, "Open"), (21, "Open")]
    with pytest.raises(AgentTaskError, match="ambiguous"):
        driver.wait_window("Open", 1)
    assert focus == []


def test_file_dialog_rebinds_only_to_confirmed_own_foreground_and_canonicalizes_path(monkeypatch, tmp_path):
    from je_auto_control.utils.agent_runtime import file_dialog_scope
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver, handle_file_dialog
    from je_auto_control.wrapper import window_backends
    focus, input_calls = [], []
    spec = AgentTaskSpec.from_dict({"goal": "open", "roots": [str(tmp_path)], "apps": ["editor"],
        "allowed_tools": ["AC_handle_file_dialog"], "success_criteria": [{"kind": "actions_complete"}]})
    backend = SimpleNamespace(list_windows=lambda: [(20, "Open")], window_process_id=lambda _hwnd: 7,
                              bring_to_front=lambda hwnd: focus.append(hwnd) or True)
    target = SimpleNamespace(_action_identity=(11, 7), _check_foreground=lambda: (20, "Open", 7))
    monkeypatch.setattr(window_backends, "get_backend", lambda: backend)
    monkeypatch.setattr(FileDialogDriver, "type_path", lambda _self, path: input_calls.append(path))
    monkeypatch.setattr(FileDialogDriver, "confirm", lambda _self, key: input_calls.append(key))
    monkeypatch.chdir(tmp_path)
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        with file_dialog_scope.scoped_file_dialog(target, 11, 7, {}):
            assert handle_file_dialog("report.txt")["handled"]
    assert focus == [20] and target._action_identity == (20, 7)
    assert input_calls == [str((tmp_path / "report.txt").resolve()), "enter"]


def test_review_error_type_survives_the_native_channel_boundary():
    import queue
    import time
    from je_auto_control.utils.agent_runtime import AgentHumanReview
    from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
    channel = object.__new__(OwnedChannel)
    channel._replies = queue.Queue()
    channel._replies.put({"id": "fixture", "error_type": "AgentHumanReview", "error": "unsaved content"})
    with pytest.raises(AgentHumanReview):
        channel._receive("fixture", time.monotonic() + 1, lambda: None, None)


def test_local_http_review_type_and_waiting_state_share_the_same_gate(tmp_path):
    from je_auto_control.utils.agent_runtime import AgentHumanReview
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService

    def observe():
        raise AgentHumanReview("unsaved content")

    target = SimpleNamespace(ready=lambda _spec: (True, ""), observe=observe, cleanup=lambda: None)
    service = AgentRuntimeService(tmp_path, targets={"fixture": target})
    try:
        service.start()
        client = AgentRuntimeClient(tmp_path / "agent_runtime.json")
        task = client.call("submit", {"spec": {"goal": "review", "target": "fixture",
            "allowed_tools": ["AC_click_mouse"], "success_criteria": [{"kind": "actions_complete"}]}})
        with pytest.raises(AgentHumanReview):
            client.call("observe", {"task_id": task["task_id"]})
        assert client.call("get", {"task_id": task["task_id"]})["state"] == "waiting_user"
        assert not service.runtime._leases
    finally:
        service.close()
