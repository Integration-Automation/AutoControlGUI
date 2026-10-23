"""Reviewed browser files use SDK fakes and temporary roots, without browser or desktop effects."""
from concurrent.futures import CancelledError
from contextlib import closing, contextmanager
import hashlib
import io
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

import je_auto_control as ac
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskSpec, AgentTargetProfile, AgentTaskError
from je_auto_control.utils.agent_runtime.browser_commands import (
    BROWSER_TOOLS, BROWSER_ELEMENT_TOOLS, browser_session_scope, browser_link, browser_download, browser_upload,
)
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget, _open_session
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.runner import run_task
from .test_agent_browser_target import fake_sdk  # noqa: F401 - shared optional-SDK-free fixture


def scoped(root, **changes):
    return AgentTaskSpec.from_dict({"goal": "reviewed browser files", "target": "reviewed-browser", "mode": "skill",
        "roots": [str(root)], "allowed_tools": sorted(BROWSER_TOOLS | {"AC_workflow_manifest"}),
        "options": {"allowed_origins": ["https://allowed.test:443"]},
        "success_criteria": [{"kind": "actions_complete"}], **changes})


@pytest.fixture
def session(fake_sdk):  # noqa: F811 - pytest resolves the imported shared fixture by name
    value = fake_sdk[0]
    value.payload = b"owned report"
    value.link = Mock(return_value="https://allowed.test/report")
    value.upload = Mock(side_effect=lambda _selector, data, name, _frame: {
        "name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    @contextmanager
    def download(_url):
        response = io.BytesIO(value.payload)
        response.headers = {"Content-Length": str(len(value.payload))}
        yield response

    value.open_download = Mock(side_effect=download)
    return value


def test_rooted_upload_sends_frozen_bytes_with_expected_digest(session, tmp_path):
    source = tmp_path / "report.bin"
    source.write_bytes(b"reviewed")
    expected = hashlib.sha256(b"reviewed").hexdigest()
    with operation_scope(TaskOperation(scoped(tmp_path), lambda: None, None)), browser_session_scope(session):
        result = browser_upload("#file", str(source), expected)
    assert result == {"name": "report.bin", "bytes": 8, "sha256": expected}
    session.upload.assert_called_once_with("#file", b"reviewed", "report.bin", "")


def test_upload_metadata_mismatch_stops_after_one_effect(session, tmp_path):
    source = tmp_path / "report.bin"
    source.write_bytes(b"reviewed")
    session.upload.side_effect = None
    session.upload.return_value = {"name": "different.bin", "bytes": 8, "sha256": "0" * 64}
    with operation_scope(TaskOperation(scoped(tmp_path), lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError, match="metadata"):
            browser_upload("#file", str(source))
    session.upload.assert_called_once()


def test_upload_refuses_replaced_file_identity_before_exporting_bytes(session, tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import browser_transfers
    source = tmp_path / "report.bin"
    source.write_bytes(b"original")
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"replacement")
    original = browser_transfers.os.open

    def replaced(path, flags, *args, **kwargs):
        return original(replacement if path == source else path, flags, *args, **kwargs)

    monkeypatch.setattr(browser_transfers.os, "open", replaced)
    with operation_scope(TaskOperation(scoped(tmp_path), lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError, match="identity"):
            browser_upload("#file", str(source))
    session.upload.assert_not_called()


@pytest.mark.parametrize("failure", ["outside", "hash", "empty", "oversize", "directory"])
def test_upload_refuses_invalid_file_before_sdk_effect(session, tmp_path, failure):
    root = tmp_path / "root"
    root.mkdir()
    source = (tmp_path if failure == "outside" else root) / "file.bin"
    if failure == "directory":
        source.mkdir()
    else:
        source.write_bytes(b"" if failure == "empty" else b"data")
        if failure == "oversize":
            with source.open("wb") as handle:
                handle.truncate(4 * 1024 * 1024 + 1)
    with operation_scope(TaskOperation(scoped(root), lambda: None, None)), browser_session_scope(session):
        with pytest.raises((AgentTaskError, OSError)):
            browser_upload("#file", str(source), "0" * 64 if failure == "hash" else "")
    session.upload.assert_not_called()


def test_download_atomically_publishes_and_reuses_only_matching_digest(session, tmp_path):
    expected = hashlib.sha256(session.payload).hexdigest()
    with operation_scope(TaskOperation(scoped(tmp_path), lambda: None, None)), browser_session_scope(session):
        result = browser_download("https://allowed.test/report", str(tmp_path), "report.bin", expected)
        assert browser_download("https://allowed.test/report", str(tmp_path), "report.bin", expected) == result
        with pytest.raises(AgentTaskError, match="matching sha256"):
            browser_download("https://allowed.test/report", str(tmp_path), "report.bin")
    assert result["sha256"] == expected
    assert (tmp_path / "report.bin").read_bytes() == session.payload
    session.open_download.assert_called_once()
    assert not list(tmp_path.glob("*.part"))


def test_failed_digest_does_not_publish_or_leave_partial_file(session, tmp_path):
    with operation_scope(TaskOperation(scoped(tmp_path), lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError, match="sha256"):
            browser_download("https://allowed.test/report", str(tmp_path), "report.bin", "0" * 64)
    assert list(tmp_path.iterdir()) == []


def test_cancellation_is_preserved_and_never_publishes_buffered_download(session, tmp_path):
    cancelled = False

    def checkpoint():
        if cancelled:
            raise CancelledError()

    @contextmanager
    def download(_url):
        class Response(io.BytesIO):
            def read(self, size):
                nonlocal cancelled
                cancelled = True
                return super().read(size)
        response = Response(b"cancelled")
        response.headers = {}
        yield response

    session.open_download.side_effect = download
    with operation_scope(TaskOperation(scoped(tmp_path), checkpoint, None)), browser_session_scope(session):
        with pytest.raises(CancelledError):
            browser_download("https://allowed.test/report", str(tmp_path), "report.bin")
    assert list(tmp_path.iterdir()) == []


def test_foreign_sdk_context_cannot_relabel_host_cancellation_as_operation_failure(session, tmp_path):
    stopped = False

    def checkpoint():
        if stopped:
            raise CancelledError()

    @contextmanager
    def download(_url):
        nonlocal stopped
        response = io.BytesIO(b"cancelled")
        response.headers = {}
        stopped = True
        try:
            yield response
        except Exception:
            raise RuntimeError("foreign SDK operation failure") from None

    session.open_download.side_effect = download
    with operation_scope(TaskOperation(scoped(tmp_path), checkpoint, None)), browser_session_scope(session):
        with pytest.raises(CancelledError):
            browser_download("https://allowed.test/report", str(tmp_path), "report.bin")
    assert list(tmp_path.iterdir()) == []


def test_links_and_downloads_cannot_expand_task_origin_grants(session, tmp_path):
    session.link.return_value = "https://outside.test/report"
    with operation_scope(TaskOperation(scoped(tmp_path), lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError, match="origins"):
            browser_link("a")
        with pytest.raises(AgentTaskError, match="origins"):
            browser_download("https://outside.test/report", str(tmp_path), "report.bin")
    session.open_download.assert_not_called()


@pytest.mark.parametrize("marker", [None, True, 0, 2, "1", 1.0])
def test_transfer_contract_is_checked_before_startup(monkeypatch, marker):
    sdk = SimpleNamespace(contract_version=1, transfer_contract_version=marker,
                          link=Mock(), open_download=Mock(), upload=Mock(), open=Mock())
    origin = Mock()
    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai",
                        SimpleNamespace(ManagedBrowserSession=sdk, BrowserOriginPolicy=origin))
    with pytest.raises(AgentTaskError, match="transfer contract version 1"):
        _open_session(("https://allowed.test",), transfer=True)
    sdk.open.assert_not_called()
    origin.assert_not_called()


def test_core_browser_tasks_remain_compatible_without_transfer_contract(monkeypatch):
    sdk = SimpleNamespace(contract_version=1, open=Mock())
    origin = Mock()
    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai",
                        SimpleNamespace(ManagedBrowserSession=sdk, BrowserOriginPolicy=origin))
    assert _open_session(("https://allowed.test",)) is sdk.open.return_value
    sdk.open.assert_called_once_with(origin.return_value)


@pytest.mark.parametrize("missing", ["link", "open_download", "upload"])
def test_transfer_marker_cannot_substitute_for_required_sdk_methods(monkeypatch, missing):
    sdk = SimpleNamespace(contract_version=1, transfer_contract_version=1,
                          link=Mock(), open_download=Mock(), upload=Mock(), open=Mock())
    delattr(sdk, missing)
    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai",
                        SimpleNamespace(ManagedBrowserSession=sdk, BrowserOriginPolicy=Mock()))
    with pytest.raises(AgentTaskError, match="transfer contract version 1"):
        _open_session(("https://allowed.test",), transfer=True)
    sdk.open.assert_not_called()


def test_file_grants_require_explicit_roots_in_profiles_and_task_policies(tmp_path):
    with pytest.raises(AgentTaskError, match="roots"):
        TaskPolicy(scoped(tmp_path, roots=[]))
    with pytest.raises(AgentTaskError, match="roots"):
        AgentTargetProfile(name="files-browser", kind="browser", allowed_tools=("AC_browser_download",),
                           settings={"allowed_origins": ["https://allowed.test"]})


def test_new_public_commands_share_executor_mcp_model_and_builder_surfaces():
    from je_auto_control.api import core
    from je_auto_control.utils.agent_runtime.commands import COMMANDS
    from je_auto_control.utils.agent_runtime.model_tools import offered_tools
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.policy import TOOL_CAPABILITIES
    assert "AC_browser_download" not in BROWSER_ELEMENT_TOOLS
    registry = {tool.name for tool in build_default_tool_registry()}
    for name in ("link", "download", "upload"):
        function = getattr(ac, "browser_" + name)
        assert function is getattr(core, "browser_" + name)
        assert COMMANDS["AC_browser_" + name] is function
        assert "ac_browser_" + name in registry
        assert offered_tools(["AC_browser_" + name])[0]["function"]["name"] == "AC_browser_" + name
    assert TOOL_CAPABILITIES["ac_browser_link"] == "drive_input"


def test_browser_archive_uses_reviewed_link_and_independent_file_manifest(session, tmp_path):
    draft = ac.draft_agent_workflow("download_archive", {"backend": "browser", "roots": [str(tmp_path)],
        "directory": str(tmp_path / "archive"), "url": "https://allowed.test/query",
        "allowed_origins": ["https://allowed.test"], "files": [{"name": "report.bin", "selector": "#report"}]})
    assert [action["tool"] for action in draft["actions"]] == [
        "AC_browser_navigate", "AC_browser_link", "AC_browser_download", "AC_workflow_manifest"]
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(draft)
        result = run_task(runtime, task.task_id)
        assert result.state == "succeeded", result.reason
        assert (tmp_path / "archive" / "report.bin").read_bytes() == session.payload
        assert (tmp_path / "archive" / "manifest.json").is_file()
