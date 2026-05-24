"""Tests for the multi-viewer presence registry."""
import threading
from contextlib import contextmanager

import pytest

from je_auto_control.utils.remote_desktop.presence import (
    PresenceError, PresenceRegistry, ROLE_CONTROLLER, ROLE_OBSERVER,
    ViewerPresence, default_presence_registry,
)


@pytest.fixture
def registry() -> PresenceRegistry:
    return PresenceRegistry()


@contextmanager
def _isolated_default_registry():
    """Reset the singleton between tests so listener state doesn't leak."""
    from je_auto_control.utils.remote_desktop import presence as mod
    saved = mod._default_registry
    mod._default_registry = PresenceRegistry()
    try:
        yield mod._default_registry
    finally:
        mod._default_registry = saved


# === register / unregister =================================================

def test_register_returns_row(registry):
    row = registry.register("v1", "alice")
    assert isinstance(row, ViewerPresence)
    assert row.viewer_id == "v1"
    assert row.label == "alice"
    assert row.role == ROLE_OBSERVER
    assert row.cursor_x is None and row.cursor_y is None
    assert row.last_seen_iso


def test_register_with_controller_role(registry):
    row = registry.register("v1", "alice", role=ROLE_CONTROLLER)
    assert row.role == ROLE_CONTROLLER
    assert row.can_control() is True


def test_register_rejects_blank_id(registry):
    with pytest.raises(PresenceError):
        registry.register("   ", "alice")


def test_register_rejects_unknown_role(registry):
    with pytest.raises(PresenceError):
        registry.register("v1", "alice", role="superuser")


def test_unregister_returns_true_when_existed(registry):
    registry.register("v1", "alice")
    assert registry.unregister("v1") is True


def test_unregister_returns_false_when_absent(registry):
    assert registry.unregister("ghost") is False


def test_clear_drops_every_row(registry):
    registry.register("v1", "alice")
    registry.register("v2", "bob")
    registry.clear()
    assert registry.list() == []
    assert registry.count() == 0


# === update_cursor =========================================================

def test_update_cursor_updates_position(registry):
    registry.register("v1", "alice")
    row = registry.update_cursor("v1", 100, 200)
    assert row.cursor_x == 100
    assert row.cursor_y == 200


def test_update_cursor_raises_for_unknown(registry):
    with pytest.raises(PresenceError):
        registry.update_cursor("ghost", 0, 0)


def test_update_role_promotes_observer(registry):
    registry.register("v1", "alice")
    row = registry.update_role("v1", ROLE_CONTROLLER)
    assert row.role == ROLE_CONTROLLER
    assert registry.can_control("v1") is True


def test_update_role_rejects_unknown_role(registry):
    registry.register("v1", "alice")
    with pytest.raises(PresenceError):
        registry.update_role("v1", "admin")


def test_update_role_raises_for_unknown_viewer(registry):
    with pytest.raises(PresenceError):
        registry.update_role("ghost", ROLE_CONTROLLER)


# === inspection ============================================================

def test_list_returns_rows_sorted_by_id(registry):
    registry.register("v_b", "bob")
    registry.register("v_a", "alice")
    rows = registry.list()
    assert [r.viewer_id for r in rows] == ["v_a", "v_b"]


def test_controller_ids_filters_observers(registry):
    registry.register("v1", "alice", role=ROLE_CONTROLLER)
    registry.register("v2", "bob", role=ROLE_OBSERVER)
    assert registry.controller_ids() == ["v1"]


def test_can_control_returns_false_for_observer(registry):
    registry.register("v1", "alice")
    assert registry.can_control("v1") is False


def test_can_control_returns_false_for_unknown(registry):
    assert registry.can_control("ghost") is False


def test_count_tracks_rows(registry):
    assert registry.count() == 0
    registry.register("v1", "alice")
    assert registry.count() == 1


# === listeners =============================================================

def test_listener_fires_on_register(registry):
    events: list = []
    registry.add_listener(lambda vid, row: events.append((vid, row)))
    registry.register("v1", "alice")
    assert len(events) == 1
    assert events[0][0] == "v1"
    assert events[0][1] is not None


def test_listener_receives_none_on_unregister(registry):
    events: list = []
    registry.register("v1", "alice")
    registry.add_listener(lambda vid, row: events.append((vid, row)))
    registry.unregister("v1")
    assert events == [("v1", None)]


def test_listener_swallows_exceptions(registry):
    def bad(_vid, _row):
        raise RuntimeError("listener bad")

    def good(vid, _row):
        good.calls.append(vid)
    good.calls = []
    registry.add_listener(bad)
    registry.add_listener(good)
    registry.register("v1", "alice")
    assert good.calls == ["v1"]


def test_remove_listener_drops_it(registry):
    events: list = []

    def listener(vid, row):
        events.append((vid, row))
    registry.add_listener(listener)
    assert registry.remove_listener(listener) is True
    registry.register("v1", "alice")
    assert events == []


# === thread safety ========================================================

def test_concurrent_registers_do_not_lose_rows(registry):
    def writer(start: int) -> None:
        for offset in range(50):
            registry.register(f"v{start + offset}", f"label{start + offset}")
    workers = [threading.Thread(target=writer, args=(start,))
               for start in (0, 1000, 2000)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert registry.count() == 150


# === façade / executor / MCP wiring =====================================

def test_default_presence_registry_is_singleton():
    a = default_presence_registry()
    b = default_presence_registry()
    assert a is b


def test_executor_registers_presence_commands():
    from je_auto_control.utils.executor.action_executor import executor
    commands = executor.known_commands()
    assert {
        "AC_presence_register", "AC_presence_unregister",
        "AC_presence_update_cursor", "AC_presence_set_role",
        "AC_presence_list", "AC_presence_clear",
    } <= commands


def test_mcp_factory_registers_presence_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_presence_register", "ac_presence_unregister",
        "ac_presence_update_cursor", "ac_presence_set_role",
        "ac_presence_list",
    } <= names


def test_facade_exports_presence_api():
    import je_auto_control as ac
    for name in ("PresenceRegistry", "ViewerPresence", "ROLE_CONTROLLER",
                  "ROLE_OBSERVER", "default_presence_registry"):
        assert hasattr(ac, name)


def test_executor_presence_register_round_trips():
    with _isolated_default_registry() as registry:
        from je_auto_control.utils.executor.action_executor import executor
        handler = executor.event_dict["AC_presence_register"]
        result = handler("v1", "alice", role=ROLE_CONTROLLER)
        assert result["viewer_id"] == "v1"
        assert result["role"] == ROLE_CONTROLLER
        assert registry.count() == 1


def test_to_dict_round_trips():
    row = ViewerPresence(
        viewer_id="v1", label="alice", role=ROLE_OBSERVER,
        cursor_x=10, cursor_y=20, last_seen_iso="t",
    )
    assert ViewerPresence(**row.to_dict()) == row
