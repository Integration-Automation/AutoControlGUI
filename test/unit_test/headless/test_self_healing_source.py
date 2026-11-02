"""Original-step links identify captured journal snapshots without device effects."""
from pathlib import Path

import pytest

import je_auto_control as ac
from je_auto_control.utils.path_guard import PathPolicy, PathNotAllowedError


@pytest.fixture(autouse=True)
def controlled(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        pytest.fail("source inspection tests must not capture or issue input")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", forbidden)
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", lambda *_a, **_k: (1, 2))
    log = ac.HealEventLog(tmp_path / "heals.jsonl")
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator.default_heal_log", log)
    return log


def capture(path):
    ac.execute_journal_run([
        ["AC_set_var", {"name": "unrelated", "value": 3}],
        ["AC_self_heal_locate", {"template_path": "unused.png"}],
    ], path, options=ac.JournalRunOptions(run_id="chosen"))


def test_captured_heal_records_actual_source_and_reader_selects_after_filtering(controlled, tmp_path):
    path = tmp_path / "actions.jsonl"
    capture(path)
    event, = controlled.list_events()
    assert event.journal_path == str(path.resolve())
    original = path.read_bytes()
    snapshots = ac.inspect_heal_source(event.journal_path, event.run_id, event.step_id, limit=1)
    assert len(snapshots) == 1 and snapshots[0]["command"] == "AC_self_heal_locate"
    assert snapshots[0]["run_id"] == event.run_id and snapshots[0]["step_id"] == event.step_id
    assert path.read_bytes() == original


def test_uncaptured_heal_and_legacy_rows_do_not_invent_source(controlled, tmp_path):
    ac.self_heal_locate("unused.png")
    event, = controlled.list_events()
    assert event.run_id and event.step_id and event.journal_path is None
    legacy = ac.HealEventLog(tmp_path / "legacy.jsonl")
    legacy.path.write_text('{"timestamp":"then","method":"miss","coordinates":null,"duration_ms":0}\n',
                           encoding="utf-8")
    assert legacy.list_events()[0].journal_path is None


def test_run_scope_without_action_step_has_no_link(controlled, tmp_path):
    with ac.journal_scope(ac.ActionJournal(tmp_path / "actions.jsonl"), run_id="scope-only"):
        ac.self_heal_locate("unused.png")
    assert controlled.list_events()[0].journal_path is None


def test_reader_keeps_both_lifecycle_snapshots_and_validates_later_rows(controlled, tmp_path):
    path = tmp_path / "actions.jsonl"
    capture(path)
    event, = controlled.list_events()
    rows = ac.inspect_heal_source(str(path), event.run_id, event.step_id)
    assert [row["status"] for row in rows] == ["incomplete", "ok"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"broken":"later"}\n')
    with pytest.raises(ac.ActionJournalError):
        ac.inspect_heal_source(str(path), event.run_id, event.step_id, limit=1)


def test_source_metadata_is_masked_at_storage_boundary(controlled, tmp_path):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    event = ac.HealEvent("now", "image", [1, 2], 1, journal_path="private-value")
    with secret_log_scope():
        remember_secret("private-value")
        controlled.append(event)
    assert controlled.list_events()[0].journal_path == "***"
    assert "private-value" not in controlled.path.read_text(encoding="utf-8")


def test_source_reader_honors_explicit_and_revoked_roots(controlled, tmp_path):
    path = tmp_path / "actions.jsonl"
    capture(path)
    event, = controlled.list_events()
    with pytest.raises(PathNotAllowedError):
        ac.inspect_heal_source(str(path), event.run_id, event.step_id, path_policy=PathPolicy([tmp_path / "other"]))
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    with pytest.raises(PathNotAllowedError):
        ac.inspect_heal_source(str(path), event.run_id, event.step_id, path_policy=policy,
                               observer=lambda _count: policy.set_client_roots([]))


@pytest.mark.parametrize("run_id,step_id", [(None, "step"), ("run", None), ("", "step"), ("run", 3)])
def test_source_identifiers_are_required_before_file_io(monkeypatch, run_id, step_id):
    monkeypatch.setattr("je_auto_control.utils.action_journal.inspection.read_events",
                        lambda *_a, **_k: pytest.fail("invalid identifiers must not open a file"))
    with pytest.raises(ac.SelfHealRequestError):
        ac.inspect_heal_source("missing.jsonl", run_id, step_id)


def test_step_filter_requires_valid_identifier_before_io(monkeypatch):
    monkeypatch.setattr("je_auto_control.utils.action_journal.inspection.read_events",
                        lambda *_a, **_k: pytest.fail("invalid step must not open a file"))
    with pytest.raises(ac.ActionJournalError):
        ac.inspect_journal(Path("missing.jsonl"), step_id=3)


def test_same_step_identifier_in_other_run_does_not_match(controlled, tmp_path):
    from dataclasses import replace
    path = tmp_path / "actions.jsonl"
    capture(path)
    event, = controlled.list_events()
    first = ac.read_events(path, run_id=event.run_id)[-1]
    ac.ActionJournal(path).append(replace(first, run_id="other", sequence=0))
    assert len(ac.inspect_heal_source(str(path), event.run_id, event.step_id)) == 2


def test_resolved_source_path_containing_current_secret_is_unknown(controlled, monkeypatch, tmp_path):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    from je_auto_control.utils.executor.action_executor import executor
    directory = tmp_path / "sensitive-parent"
    directory.mkdir()
    monkeypatch.chdir(directory)
    with secret_log_scope():
        remember_secret("sensitive-parent")
        with ac.journal_scope(ac.ActionJournal(Path("events.jsonl")), run_id="chosen"):
            executor.execute_action([["AC_self_heal_locate", {"template_path": "unused.png"}]], raise_on_error=True)
    assert controlled.list_events()[0].journal_path is None


def test_commands_cli_mcp_and_builder_read_the_same_source(controlled, tmp_path, capsys):
    import json
    from je_auto_control.cli import main
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.policy import capability_for_tool
    path = tmp_path / "actions.jsonl"
    capture(path)
    event, = controlled.list_events()
    arguments = {"path": event.journal_path, "run_id": event.run_id, "step_id": event.step_id}
    actions = [["AC_self_heal_source", arguments]]
    record = executor.execute_action(actions, raise_on_error=True)
    tool = next(tool for tool in build_default_tool_registry() if tool.name == "ac_self_heal_source")
    remote = tool.handler(**arguments)
    assert next(iter(record.values())) == remote
    assert tool.annotations.read_only and capability_for_tool(tool.name, True) == "drive_input"
    assert {field.name for field in COMMAND_SPECS["AC_self_heal_source"].fields} == {*arguments, "limit"}
    script = tmp_path / "source.json"
    script.write_text(json.dumps(actions), encoding="utf-8")
    assert main(["run", str(script)]) == 0
    assert '"AC_self_heal_locate"' in capsys.readouterr().out


def test_source_command_refuses_viewer_before_io(monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
    from je_auto_control.utils.rbac.authorization import AuthorizationError
    monkeypatch.setattr("je_auto_control.utils.action_journal.inspection.read_events",
                        lambda *_a, **_k: pytest.fail("a viewer must not open private source data"))
    with authorization_scope(AuthorizationContext("reader", Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            executor.execute_action([["AC_self_heal_source", {"path": "private.jsonl", "run_id": "r", "step_id": "s"}]],
                                    raise_on_error=True)


def test_mcp_source_cancellation_keeps_original_signal(controlled, tmp_path):
    from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    path = tmp_path / "actions.jsonl"
    capture(path)
    event, = controlled.list_events()
    ctx = ToolCallContext("source", progress_token="p")

    def notify(_method, params):
        if params["progress"] == 1:
            ctx.cancelled_event.set()

    ctx.notifier = notify
    tool = next(tool for tool in build_default_tool_registry() if tool.name == "ac_self_heal_source")
    with pytest.raises(OperationCancelledError):
        tool.handler(str(path), event.run_id, event.step_id, ctx=ctx)
