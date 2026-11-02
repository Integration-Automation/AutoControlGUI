"""Named-body executor adapter for explicit manual run-history ownership."""
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.run_history.manual import manual_history_scope


def _history_capture_body(*, body: list[object], source_id: str = "script",
                          script_path: str = "<actions>") -> dict[str, object]:
    """Record a named body on its owning executor without eager interpolation."""
    # pylint: disable-next=import-outside-toplevel  # reason: the executor registers this adapter
    from je_auto_control.utils.executor.action_executor import _running_executor, recorded_failures
    runner = _running_executor()
    validate_actions(body, runner.known_commands())
    with manual_history_scope(source_id=source_id, script_path=script_path) as owner:
        before = recorded_failures()
        record: dict[str, object] = dict(runner.execute_action(body, _validated=True))
    return {"history_id": owner.run_id, "record": record, "failed_actions": recorded_failures() - before}
