"""Four complete managed workflows over local HTTP, files and fake semantic applications."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, draft_agent_workflow
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.runner import run_task


class Applications:
    def __init__(self):
        self.values = {"Source": "  Ada  ", "Confirmation": "ready"}
        self.submissions = 0
        self.opened = []
        self.fail_readback = False

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return {"identity": "applications", "elements": []}

    def perform(self, tool, arguments):
        if tool == "AC_focus_window":
            return 42
        if tool == "AC_snap_window":
            return {"moved": True}
        if tool == "AC_workflow_open":
            self.opened.append(arguments["path"])
            return True
        selector = arguments["selector"]["name"]
        if tool == "AC_workflow_wait":
            if arguments.get("state"):
                return {"read_only": False}
            return "wrong" if self.fail_readback else self.values.get(selector, "")
        operation = arguments["operation"]
        if operation == "state":
            return {"read_only": False}
        if operation == "set":
            self.values[selector] = arguments["value"]
            return True
        if operation == "get":
            return "wrong" if self.fail_readback else self.values.get(selector, "")
        if selector == "New":
            self.values["Confirmation"] = "ready"
            return True
        self.submissions += 1
        self.values["Confirmation"] = "saved"
        return True

    def cleanup(self):
        return None


def selector(name):
    return {"name": name, "app_name": "fixture"}


def commit_config():
    return {"submit_selector": selector("Save"), "confirmation_selector": selector("Confirmation"),
            "confirmation_value": "saved", "new_record_selector": selector("New")}


@pytest.fixture
def apps(tmp_path):
    target = Applications()
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"local-desktop": target, "local-files": FileTarget()})
    yield runtime, target
    runtime.close()


def execute(runtime, workflow, config):
    draft = draft_agent_workflow(workflow, config)
    task = runtime.submit(draft)
    return task, run_task(runtime, task.task_id)


def test_csv_batch_validates_and_reads_back_each_row_before_submit(apps, tmp_path):
    runtime, target = apps
    source = tmp_path / "rows.csv"
    source.write_text("name\nAda\nGrace\n", encoding="utf-8")
    task, result = execute(runtime, "batch_form", {"roots": [str(tmp_path)], "apps": ["fixture"],
        "source": str(source), "window_title": "Form", "fields": [{"column": "name", "selector": selector("Name")}],
        **commit_config()})
    assert result.state == "succeeded"
    assert target.submissions == 2
    assert len(runtime.store.actions(task.task_id)) == 13


def test_stale_saved_label_never_causes_a_duplicate_submission(apps, tmp_path):
    runtime, target = apps
    target.values["Confirmation"] = "saved"
    source = tmp_path / "rows.csv"
    source.write_text("name\nAda\n", encoding="utf-8")
    config = {key: value for key, value in commit_config().items() if key != "new_record_selector"}
    task, result = execute(runtime, "batch_form", {"roots": [str(tmp_path)], "apps": ["fixture"],
        "source": str(source), "window_title": "Form", "fields": [{"column": "name", "selector": selector("Name")}],
        **config})
    assert result.state == "waiting_user"
    assert target.submissions == 0
    assert runtime.receipts(task.task_id)["rows"] == [{"row": "1", "status": "failed"}]
    runtime.resume(task.task_id)
    assert run_task(runtime, task.task_id).state == "waiting_user"
    assert target.submissions == 0


def test_readback_mismatch_stops_before_submission(apps, tmp_path):
    runtime, target = apps
    source = tmp_path / "rows.csv"
    source.write_text("name\nAda\n", encoding="utf-8")
    target.fail_readback = True
    _task, result = execute(runtime, "batch_form", {"roots": [str(tmp_path)], "apps": ["fixture"],
        "source": str(source), "window_title": "Form", "fields": [{"column": "name", "selector": selector("Name")}],
        **commit_config()})
    assert result.state == "waiting_user"
    assert target.submissions == 0
    assert not runtime._leases


def test_transfer_captures_transforms_reads_back_and_confirms_save(apps):
    runtime, target = apps
    _task, result = execute(runtime, "transfer", {"apps": ["fixture"],
        "source_app": {"window_title": "Source"}, "destination_app": {"window_title": "Destination"},
        "fields": [{"source": selector("Source"), "destination": selector("Destination"), "transform": "strip"}],
        **commit_config()})
    assert result.state == "succeeded"
    assert target.values["Destination"] == "Ada"
    assert target.submissions == 1


def test_workspace_opens_only_explicit_documents_and_checks_window_readiness(apps, tmp_path):
    runtime, target = apps
    document = tmp_path / "report.txt"
    document.write_text("report", encoding="utf-8")
    _task, result = execute(runtime, "workspace", {"roots": [str(tmp_path)], "apps": ["fixture"],
        "documents": [str(document)], "windows": [{"window_title": "Editor", "position": "left",
            "ready_selector": selector("Document"), "ready_state": {"read_only": False}}]})
    assert result.state == "succeeded"
    assert target.opened == [str(document)]


def test_download_archive_checks_content_and_writes_manifest(apps, tmp_path):
    runtime, _target = apps
    data = b"local fixture content"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        task, result = execute(runtime, "download_archive", {"roots": [str(tmp_path)], "directory": str(tmp_path),
            "files": [{"url": f"http://127.0.0.1:{server.server_port}/report", "name": "report.txt",
                       "sha256": hashlib.sha256(data).hexdigest()}]})
        assert result.state == "succeeded"
        assert (tmp_path / "report.txt").read_bytes() == data
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["files"][0]["bytes"] == len(data)
        assert len(runtime.store.actions(task.task_id)) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_source_path_cannot_escape_roots(tmp_path):
    with pytest.raises(AgentTaskError):
        draft_agent_workflow("batch_form", {"roots": [str(tmp_path / "allowed")], "source": str(tmp_path / "outside.csv")})


def test_file_workflow_runs_in_real_owned_helper_without_desktop_input(tmp_path):
    source = tmp_path / "report.txt"
    source.write_text("fixture", encoding="utf-8")
    runtime = AgentRuntime(tmp_path / "runtime.sqlite")
    try:
        task = runtime.submit({"goal": "manifest fixture", "target": "local-files", "mode": "skill",
            "allowed_tools": ["AC_workflow_manifest"], "roots": [str(tmp_path)],
            "success_criteria": [{"kind": "actions_complete"}],
            "actions": [{"tool": "AC_workflow_manifest", "arguments": {"directory": str(tmp_path),
                "path": str(tmp_path / "manifest.json"), "names": [source.name]}}]})
        result = run_task(runtime, task.task_id)
        assert result.state == "succeeded", result.reason
        assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["files"][0]["name"] == source.name
        assert not runtime._leases
    finally:
        runtime.close()


@pytest.mark.parametrize("name", ["../outside", "NUL.txt", "report.txt.", "report\\bad", "report.txt:stream"])
def test_archive_preview_rejects_nonportable_or_escaping_filenames(tmp_path, name):
    with pytest.raises(AgentTaskError):
        draft_agent_workflow("download_archive", {"roots": [str(tmp_path)], "directory": str(tmp_path),
            "files": [{"url": "http://127.0.0.1/report", "name": name}]})
