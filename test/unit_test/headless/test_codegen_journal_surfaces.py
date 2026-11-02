"""Adapters export the same review artifact and protect private journal reads."""
import json
import zipfile

import pytest

from headless import test_codegen_from_journal as fixtures
from je_auto_control import executor
from je_auto_control.cli import main
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool

journal = fixtures.journal
forbid_dispatch = fixtures.forbid_dispatch


def tool():
    return next(item for item in build_default_tool_registry() if item.name == "ac_generate_candidate_from_log")


def test_command_mcp_and_builder_share_review_schema(journal):
    fixtures.append_step(journal, "kept")
    arguments = {"path": str(journal.path), "run_id": "selected"}
    command = executor.event_dict["AC_generate_candidate_from_log"](**arguments)
    via_mcp = tool().handler(**arguments)
    assert command == via_mcp
    assert command["manifest"]["run_id"] == "selected"
    assert "AC_generate_candidate_from_log" in COMMAND_SPECS
    assert capability_for_tool(tool().name, True) == "drive_input"


def test_cli_from_log_returns_source_and_manifest(journal, capsys):
    fixtures.append_step(journal, "kept")
    assert main(["codegen", "--from-log", str(journal.path), "--run-id", "selected"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["manifest"]["style"] == "actions"
    assert data["manifest"]["observed_path_only"] is True
    assert "def test_journal_candidate" in data["code"]


def test_cli_explicit_export_is_a_single_complete_zip(journal, tmp_path, capsys):
    fixtures.append_step(journal, "kept")
    output = tmp_path / "review.zip"
    assert main(["codegen", "--from-log", str(journal.path), "--run-id", "selected", "-o", str(output)]) == 0
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"candidate.py", "manifest.json", "actions.json", "README.txt"}
        assert json.loads(archive.read("manifest.json"))["run_id"] == "selected"
        assert json.loads(archive.read("actions.json")) == [["AC_sleep", {"seconds": 0}]]
    assert str(output) in capsys.readouterr().err


def test_viewer_cannot_read_journals_even_for_read_only_generation():
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            authorize_command("AC_generate_candidate_from_log")


def test_cancelled_mcp_request_never_reads_source(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("cancelled candidate generation must not open a private journal")
    monkeypatch.setattr("je_auto_control.utils.codegen.journal_source.Path.open", forbidden)
    context = ToolCallContext("candidate")
    context.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tool().handler("private.jsonl", "selected", ctx=context)


def test_archive_checks_cached_review_and_leaves_existing_file_on_replace_failure(journal, tmp_path, monkeypatch):
    fixtures.append_step(journal, "kept")
    from je_auto_control import generate_candidate_from_log, write_candidate_archive
    candidate = generate_candidate_from_log(journal.path, run_id="selected")
    output = tmp_path / "review.zip"
    output.write_bytes(b"previous archive")

    def fail(*_args):
        raise OSError("controlled replace failure")

    monkeypatch.setattr("je_auto_control.utils.json_store.json_store._replace", fail)
    with pytest.raises(OSError):
        write_candidate_archive(candidate, output)
    assert output.read_bytes() == b"previous archive"


def test_export_cannot_write_a_changed_candidate_with_stale_hashes(journal, tmp_path):
    fixtures.append_step(journal, "kept")
    from je_auto_control import CandidateGenerationError, generate_candidate_from_log, write_candidate_archive
    candidate = generate_candidate_from_log(journal.path, run_id="selected")
    candidate.actions.append(["AC_sleep", {"seconds": 99}])
    output = tmp_path / "review.zip"
    with pytest.raises(CandidateGenerationError, match="changed after review"):
        write_candidate_archive(candidate, output)
    assert not output.exists()


def test_cancel_at_export_checkpoint_keeps_previous_artifact(journal, tmp_path):
    from concurrent.futures import CancelledError
    from je_auto_control import generate_candidate_from_log, write_candidate_archive
    fixtures.append_step(journal, "kept")
    candidate = generate_candidate_from_log(journal.path, run_id="selected")
    output = tmp_path / "review.zip"
    output.write_bytes(b"previous archive")

    def cancel(count):
        if count == 1:
            raise CancelledError("cancel export before replace")

    with pytest.raises(CancelledError):
        write_candidate_archive(candidate, output, observer=cancel)
    assert output.read_bytes() == b"previous archive"


def test_export_refuses_provenance_mutated_after_review(journal, tmp_path):
    from je_auto_control import CandidateGenerationError, generate_candidate_from_log, write_candidate_archive
    fixtures.append_step(journal, "kept")
    candidate = generate_candidate_from_log(journal.path, run_id="selected")
    candidate.manifest["run_id"] = "unrelated-run"
    output = tmp_path / "review.zip"
    with pytest.raises(CandidateGenerationError, match="changed after review"):
        write_candidate_archive(candidate, output)
    assert not output.exists()
