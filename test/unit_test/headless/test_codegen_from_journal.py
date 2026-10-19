"""Journal candidates retain source evidence without replaying device actions."""
import ast
from dataclasses import replace

import pytest

import je_auto_control as ac
from je_auto_control.utils.action_journal import ActionEvent, ActionJournal


@pytest.fixture(autouse=True)
def forbid_dispatch(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("candidate generation must never dispatch an action")
    monkeypatch.setattr(ac.executor, "_execute_event", forbidden)
    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", forbidden)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.get_backend", forbidden)


def append_step(journal, step, command="AC_sleep", parameters=None, *, run="selected", parent=None, status="ok"):
    event = ActionEvent(run, step, command, {"seconds": 0} if parameters is None else parameters,
                        1.0, parent_id=parent)
    journal.append(event)
    if status != "incomplete":
        journal.append(replace(event, status=status, finished_at=2.0))


@pytest.fixture
def journal(tmp_path):
    return ActionJournal(tmp_path / "source.jsonl")


def candidate(journal, **options):
    return ac.generate_candidate_from_log(journal.path, run_id="selected", **options)


def test_run_filter_and_provenance(journal):
    append_step(journal, "other-step", run="other")
    append_step(journal, "chosen")
    generated = candidate(journal)
    assert generated.manifest["run_id"] == "selected"
    assert generated.actions == [["AC_sleep", {"seconds": 0}]]
    assert generated.manifest["steps"][0]["sequences"] == [3, 4]
    assert generated.manifest["steps"][0]["line_numbers"] == [3, 4]
    assert generated.manifest["source_sha256"]
    assert "other-step" not in generated.code
    ast.parse(generated.code)


def test_observed_branch_is_labelled(journal):
    # Legacy/partial source has the observed child but no branch bodies.
    event = ActionEvent("selected", "branch", "AC_if_var", {"name": "mode"}, 1.0)
    journal.append(event)
    append_step(journal, "observed", parent="branch")
    journal.append(replace(event, status="ok", finished_at=3.0))
    generated = candidate(journal)
    assert generated.observed_path_only is True
    assert generated.actions == [["AC_sleep", {"seconds": 0}]]
    assert any("observed" in warning for warning in generated.warnings)
    assert generated.manifest["steps"][1]["parent_id"] == "branch"


def test_secret_reference_survives_codegen(journal):
    append_step(journal, "reference", command="AC_write_secret", parameters={"secret": "${secrets.login}"})
    generated = candidate(journal)
    assert "${secrets.login}" in generated.code
    assert generated.actions == [["AC_write_secret", {"secret": "${secrets.login}"}]]


def test_generation_has_no_device_effect(journal, monkeypatch):
    append_step(journal, "click", command="AC_click_mouse", parameters={"mouse_keycode": "left", "x": 12, "y": 34})
    calls = []
    monkeypatch.setattr(ac.executor, "_execute_event", lambda *_args: calls.append("dispatch"))
    generated = candidate(journal)
    assert calls == []
    assert generated.actions[0][0] == "AC_click_mouse"
    assert generated.manifest["validation"]["dry_run"] == "passed"
    assert generated.manifest["validation"]["dispatches"] == 0


def test_recorded_loop_keeps_source_and_does_not_duplicate_iterations(journal):
    source = ActionEvent("selected", "loop", "AC_loop", {
        "times": 2, "body": [["AC_sleep", {"seconds": 0}]],
    }, 1.0)
    journal.append(source)
    append_step(journal, "first", parent="loop")
    append_step(journal, "second", parent="loop")
    journal.append(replace(source, status="ok", finished_at=3.0))
    generated = candidate(journal)
    assert generated.actions == [["AC_loop", source.parameters]]
    assert [step["emission"] for step in generated.manifest["steps"]] == [
        "recorded_source", "covered_by_parent", "covered_by_parent",
    ]


def test_retry_retains_failed_attempt_evidence_without_replaying_it_twice(journal):
    source = ActionEvent("selected", "retry", "AC_retry", {
        "max_attempts": 2, "backoff": 0, "body": [["AC_sleep", {"seconds": 0}]],
    }, 1.0)
    journal.append(source)
    append_step(journal, "failure", parent="retry", status="error")
    append_step(journal, "success", parent="retry")
    journal.append(replace(source, status="ok", finished_at=3.0))
    generated = candidate(journal)
    assert generated.actions == [["AC_retry", source.parameters]]
    assert generated.manifest["steps"][0]["retry_attempts"] == [["failure"], ["success"]]


def test_failed_and_incomplete_roots_do_not_promote_successful_children(journal):
    append_step(journal, "unfinished", status="incomplete")
    source = ActionEvent("selected", "failed", "AC_loop", {"times": 1}, 1.0)
    journal.append(source)
    append_step(journal, "child", parent="failed")
    journal.append(replace(source, status="error", finished_at=3.0))
    append_step(journal, "kept")
    generated = candidate(journal)
    assert generated.actions == [["AC_sleep", {"seconds": 0}]]
    assert {step["step_id"] for step in generated.manifest["steps"] if step["emission"] == "excluded"} == {
        "unfinished", "failed", "child",
    }


def test_unknown_command_and_redacted_input_are_excluded_with_reasons(journal):
    append_step(journal, "unknown", command="AC_not_installed", parameters={})
    append_step(journal, "redacted", command="AC_write_secret", parameters={"secret": "never-persist-this"})
    append_step(journal, "kept")
    generated = candidate(journal)
    assert generated.actions == [["AC_sleep", {"seconds": 0}]]
    assert "never-persist-this" not in str(generated.to_dict())
    assert all(step["reasons"] for step in generated.manifest["steps"][:2])


def test_completion_must_match_its_start(journal):
    source = ActionEvent("selected", "changed", "AC_sleep", {"seconds": 0}, 1.0)
    journal.append(source)
    journal.append(replace(source, parameters={"seconds": 1}, status="ok", finished_at=2.0))
    with pytest.raises(ac.CandidateGenerationError):
        candidate(journal)


def test_generation_does_not_append_to_enclosing_journal(journal, tmp_path):
    append_step(journal, "kept")
    enclosing = ActionJournal(tmp_path / "enclosing.jsonl")
    with ac.journal_scope(enclosing):
        candidate(journal)
    assert not enclosing.path.exists()


@pytest.mark.parametrize("target", ["pytest", "python", "robot"])
def test_all_targets_are_generated_without_dispatch(journal, target):
    append_step(journal, "kept")
    generated = candidate(journal, target=target)
    assert generated.code and generated.manifest["target"] == target
    assert generated.manifest["validation"]["static"] == "passed"


def test_positional_and_argument_free_snapshots_keep_their_actual_call_shapes(journal):
    append_step(journal, "no-args", command="AC_screen_size", parameters={"args": []})
    append_step(journal, "positional", command="AC_click_mouse", parameters={"args": [["left", 12, 34]]})
    generated = candidate(journal)
    assert generated.actions == [["AC_screen_size"], ["AC_click_mouse", ["left", 12, 34]]]


def test_parallel_recorded_branches_remain_parallel(journal):
    source = ActionEvent("selected", "parallel", "AC_parallel", {
        "branches": [[["AC_sleep", {"seconds": 0}]], [["AC_sleep", {"seconds": 1}]]],
    }, 1.0)
    journal.append(source)
    append_step(journal, "left", parent="parallel")
    append_step(journal, "right", parent="parallel", parameters={"seconds": 1})
    journal.append(replace(source, status="ok", finished_at=3.0))
    generated = candidate(journal)
    assert generated.actions == [["AC_parallel", source.parameters]]


def test_missing_parallel_source_is_not_fabricated_as_a_serial_script(journal):
    source = ActionEvent("selected", "parallel", "AC_parallel", {}, 1.0)
    journal.append(source)
    append_step(journal, "left", parent="parallel")
    journal.append(replace(source, status="ok", finished_at=3.0))
    generated = candidate(journal)
    assert generated.actions == []
    assert "raise RuntimeError" in generated.code
    assert all(step["emission"] == "excluded" for step in generated.manifest["steps"])
    assert any("parallel" in warning for warning in generated.warnings)


def test_start_without_completion_never_generates_a_passing_empty_test(journal):
    append_step(journal, "unfinished", status="incomplete")
    generated = candidate(journal)
    assert generated.actions == []
    namespace = {}
    exec(compile(generated.code, "candidate.py", "exec"), namespace)
    with pytest.raises(RuntimeError, match="No replayable"):
        namespace["test_journal_candidate"]()


def test_corrupt_other_run_is_not_hidden_by_selection(journal):
    append_step(journal, "kept")
    with journal.path.open("ab") as handle:
        handle.write(b'{"run_id":"other","broken":true}\n')
    with pytest.raises(ac.CandidateGenerationError, match="invalid journal record"):
        candidate(journal)


def test_duplicate_nested_json_keys_are_not_silently_accepted(journal):
    append_step(journal, "kept")
    data = journal.path.read_text(encoding="utf-8").replace('"seconds":0', '"seconds":0,"seconds":1', 1)
    journal.path.write_text(data, encoding="utf-8")
    with pytest.raises(ac.CandidateGenerationError):
        candidate(journal)


def test_uncommitted_tail_has_snapshot_hash_and_remains_unchanged(journal):
    import hashlib
    append_step(journal, "kept")
    with journal.path.open("ab") as handle:
        handle.write(b'{"torn":')
    before = journal.path.read_bytes()
    generated = candidate(journal)
    assert generated.manifest["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert generated.manifest["ignored_torn_tail"] is True
    assert journal.path.read_bytes() == before


def test_source_mutation_during_progress_does_not_change_consumed_snapshot(journal):
    import hashlib
    append_step(journal, "kept")
    before = journal.path.read_bytes()

    def mutate(count):
        if count == 1:
            journal.path.write_text("changed after snapshot", encoding="utf-8")

    generated = candidate(journal, observer=mutate)
    assert generated.actions == [["AC_sleep", {"seconds": 0}]]
    assert generated.manifest["source_sha256"] == hashlib.sha256(before).hexdigest()


def test_source_roots_are_rechecked_after_progress(journal):
    from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
    append_step(journal, "kept")
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([journal.path.parent])

    def revoke(count):
        if count == 1:
            policy.set_client_roots([])

    with pytest.raises(PathNotAllowedError):
        candidate(journal, observer=revoke, path_policy=policy)


def test_cancelled_generation_does_not_publish_a_partial_candidate(journal):
    from concurrent.futures import CancelledError
    append_step(journal, "kept")

    def cancel(count):
        if count:
            raise CancelledError("cancel review")

    with pytest.raises(CancelledError):
        candidate(journal, observer=cancel)


def test_masking_cannot_invalidate_code_after_it_is_reported_as_valid(journal):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    append_step(journal, "kept")
    with secret_log_scope():
        remember_secret("0")
        with pytest.raises(ac.CandidateGenerationError, match="resolved-secret mask"):
            candidate(journal)


def test_literal_log_content_is_never_evaluated(journal, tmp_path):
    marker = tmp_path / "must-not-exist.txt"
    text = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')"
    append_step(journal, "text", command="AC_set_var", parameters={"name": "data", "value": text})
    generated = candidate(journal, style="calls")
    assert not marker.exists()
    assert generated.actions[0][1]["value"] == text
    ast.parse(generated.code)


def test_duplicate_step_completion_is_refused(journal):
    append_step(journal, "duplicate")
    event = ac.read_events(journal.path)[-1]
    journal.append(event)
    with pytest.raises(ac.CandidateGenerationError, match="lifecycle"):
        candidate(journal)


def test_source_budget_is_enforced_before_reconciling(journal, monkeypatch):
    append_step(journal, "kept")
    monkeypatch.setattr("je_auto_control.utils.codegen.journal_source.MAX_SOURCE_BYTES", 16)
    with pytest.raises(ac.CandidateGenerationError, match="64 MiB"):
        candidate(journal)


def test_encoded_parallel_source_preserves_exact_argument_text_and_references(journal):
    import json
    encoded = ' [[ ["AC_write_secret", {"secret": "${secrets.login}"}] ]] '
    append_step(journal, "parallel", command="AC_parallel", parameters={"branches": encoded})
    generated = candidate(journal)
    assert generated.actions == [["AC_parallel", {"branches": encoded}]]
    assert "${secrets.login}" in json.dumps(generated.to_dict())


def test_encoded_parallel_source_masks_secrets_before_journal_write(journal):
    import json
    secret = "encoded-private-password"
    encoded = json.dumps([[["AC_write_secret", {"secret": secret}]]])
    append_step(journal, "parallel", command="AC_parallel", parameters={"branches": encoded})
    assert secret not in journal.path.read_text(encoding="utf-8")
    generated = candidate(journal)
    assert generated.actions == []
    assert all(step["reasons"] for step in generated.manifest["steps"])


def test_nested_and_positional_secret_references_survive_storage_and_generation(journal):
    append_step(journal, "positional-ref", command="AC_write_secret", parameters={"args": [["${secrets.login}"]]})
    append_step(journal, "loop-ref", command="AC_loop", parameters={
        "times": 1, "body": [["AC_write_secret", {"secret": "${secrets.login}"}]],
    })
    generated = candidate(journal)
    assert generated.actions == [
        ["AC_write_secret", ["${secrets.login}"]],
        ["AC_loop", {"times": 1, "body": [["AC_write_secret", {"secret": "${secrets.login}"}]]}],
    ]


def test_duplicate_encoded_secret_keys_are_omitted_before_storage(journal):
    encoded = '[[["AC_write_secret", {"secret":"hidden-first-value","secret":"${secrets.login}"}]]]'
    append_step(journal, "parallel", command="AC_parallel", parameters={"branches": encoded})
    assert "hidden-first-value" not in journal.path.read_text(encoding="utf-8")
    assert candidate(journal).actions == []


@pytest.mark.parametrize("dynamic_key", [False, True])
def test_known_resolved_secret_in_ordinary_source_value_is_masked_before_write(journal, dynamic_key):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    secret = "resolved-long-private-value"
    with secret_log_scope():
        remember_secret(secret)
        value = {secret: "data"} if dynamic_key else secret
        append_step(journal, "known", command="AC_set_var", parameters={"name": "data", "value": value})
    assert secret not in journal.path.read_text(encoding="utf-8")


def test_real_virtual_retry_capture_is_reconciled_without_reexecuting_attempts(journal, monkeypatch):
    from je_auto_control.utils.executor.action_executor import Executor
    fresh = Executor()
    calls = []

    def transient():
        calls.append("virtual attempt")
        if len(calls) == 1:
            raise ac.AutoControlActionException("controlled transient")

    fresh.event_dict["AC_test_virtual_transient"] = transient
    monkeypatch.setitem(ac.executor.event_dict, "AC_test_virtual_transient", transient)
    dispatch = fresh._execute_event

    def virtual_only(action):
        assert action[0] in {"AC_retry", "AC_test_virtual_transient"}
        return dispatch(action)

    monkeypatch.setattr(fresh, "_execute_event", virtual_only)
    actions = [["AC_retry", {"max_attempts": 2, "backoff": 0, "body": [["AC_test_virtual_transient"]]}]]
    with ac.journal_scope(journal, run_id="selected"):
        fresh.execute_action(actions, raise_on_error=True)
    assert len(calls) == 2
    generated = candidate(journal)
    assert generated.actions == actions
    assert len(generated.manifest["steps"][0]["retry_attempts"]) == 2
    assert len(calls) == 2
