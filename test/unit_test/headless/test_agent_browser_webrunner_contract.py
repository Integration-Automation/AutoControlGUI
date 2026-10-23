"""Optional source-to-source WebRunner contracts use only fake Chromium and owned loopback/IPC."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("je_web_runner", reason="reviewed optional WebRunner SDK is not installed")

from je_web_runner.api.ai import BrowserOriginPolicy  # noqa: E402 - optional SDK guard
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTargetProfile, AgentTaskSpec  # noqa: E402
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget  # noqa: E402
from je_auto_control.utils.agent_runtime.runner import run_task  # noqa: E402


def fake_runtime(*, hang=False, transfers=False):
    """The real SDK lifecycle sees an event-capable fake page; no engine API is imported."""
    state = {"value": "", "url": "about:blank"}
    events = {}
    page, context, browser, runtime, factory = (MagicMock() for _index in range(5))
    del page.execute_script  # Match Playwright's interface; do not accidentally select Selenium dispatch.
    page.url = "about:blank"
    context.on.side_effect = lambda name, callback: events.setdefault(name, []).append(callback)
    context.cookies.return_value = []

    def new_page():
        context.route.assert_called_once()
        context.route_web_socket.assert_called_once()
        for callback in events["page"]:
            callback(page)
        return page

    def fill(value):
        if hang:
            import time
            time.sleep(30)
        state["value"] = value

    context.new_page.side_effect = new_page
    browser.new_context.return_value = context
    runtime.chromium.launch.return_value = browser
    factory.return_value.start.return_value = runtime
    page.evaluate.side_effect = lambda *_args: {
        "url": state["url"], "title": "Form", "text": "Field",
        "elements": [{"selector": "#field", "tag": "input", "text": "Field", "role": "textbox",
                      "is_visible": True, "is_enabled": True}],
        "frames": [], "console_errors": [], "network_errors": [],
    }
    page.locator.return_value.count.return_value = 1
    element = page.locator.return_value.nth.return_value
    element.is_visible.return_value = True
    element.is_enabled.return_value = True
    element.fill.side_effect = fill
    def evaluate(script):
        if transfers and "element.tagName === 'INPUT'" in script:
            return True
        if transfers and "[...element.files]" in script:
            return state.get("files", [])
        if transfers and "element.href" in script:
            return state["url"].rsplit("/", 1)[0] + "/file"
        return state["value"]

    def upload(payload):
        state["files"] = [{"name": payload["name"], "size": len(payload["buffer"])}]

    element.evaluate.side_effect = evaluate
    element.set_input_files.side_effect = upload

    def navigate(url, **_options):
        page.url = url
        state["url"] = url

    page.goto.side_effect = navigate
    return factory


def configuration():
    return AgentTargetProfile(name="contract-browser", kind="browser",
        allowed_tools=("AC_browser_fill", "AC_browser_read"), settings={"allowed_origins": ["https://allowed.test"]})


def specification(seconds=30):
    return AgentTaskSpec.from_dict({"goal": "fill and read back", "target": "contract-browser", "mode": "skill",
        "allowed_tools": ["AC_browser_fill", "AC_browser_read"],
        "options": {"allowed_origins": ["https://allowed.test"]}, "budget": {"action_seconds": seconds},
        "success_criteria": [{"kind": "actions_complete"}],
        "actions": [{"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "reviewed"}},
                    {"tool": "AC_browser_read", "arguments": {"operation": "value", "selector": "#field"},
                     "expect_result": "reviewed"}]})


def test_exact_origin_contract_agrees_without_starting_a_browser():
    configuration().check(specification())
    policy = BrowserOriginPolicy(tuple(configuration().settings["allowed_origins"]))
    assert policy.origins == ("https://allowed.test",)
    assert policy.allows("https://allowed.test:443/form")
    assert not policy.allows("https://outside.test/form")


def owned_target(tmp_path, monkeypatch, *, hang=False, transfers=False):
    from je_auto_control.utils.agent_runtime import target_profiles
    script = (
        "import sys; sys.path.insert(0,sys.argv[1]); "
        "from headless.test_agent_browser_webrunner_contract import fake_runtime; "
        "from je_web_runner.webdriver import playwright_wrapper as module; "
        f"module._require_playwright=lambda:fake_runtime(hang={hang!r},transfers={transfers!r}); "
        "from je_auto_control.utils.agent_runtime.native_worker import main; main()"
    )
    adapter = NativeDesktopTarget(argv=[sys.executable, "-u", "-c", script, str(Path(__file__).parent.parent)],
                                  resource_path=tmp_path / "browser.lock", recovery_probe=lambda: None,
                                  profile=configuration().to_dict())
    monkeypatch.setattr(target_profiles, "build_target", lambda _configuration: adapter)
    return adapter


def test_real_sdk_and_owned_worker_keep_session_until_independent_readback(tmp_path, monkeypatch):
    adapter = owned_target(tmp_path, monkeypatch)
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    try:
        runtime.target_profiles.control("register", configuration().to_dict())
        handle = runtime.submit(specification())
        result = run_task(runtime, handle.task_id)
        assert result.state == "succeeded", result.reason
        receipts = runtime.store.actions(handle.task_id)
        assert [row["result"] for row in receipts] == [True, "reviewed"]
        assert adapter._channel is None
        assert adapter._resource is None
    finally:
        runtime.close()


def test_hung_sdk_effect_reaps_only_owned_helper_and_preserves_uncertainty(tmp_path, monkeypatch):
    adapter = owned_target(tmp_path, monkeypatch, hang=True)
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    try:
        runtime.target_profiles.control("register", configuration().to_dict())
        handle = runtime.submit(specification(seconds=1))
        result = run_task(runtime, handle.task_id)
        assert result.state == "waiting_user"
        receipts = runtime.store.actions(handle.task_id)
        assert len(receipts) == 1 and receipts[0]["status"] == "uncertain"
        assert adapter._channel is None
        assert adapter._ledger.empty
    finally:
        runtime.close()


def test_pinned_browser_criterion_reads_real_sdk_in_same_owned_helper(tmp_path, monkeypatch):
    reviewed = AgentTargetProfile(name="contract-browser", kind="browser",
        allowed_tools=("AC_browser_navigate", "AC_browser_fill", "AC_browser_read"),
        settings={"allowed_origins": ["https://allowed.test"]})
    monkeypatch.setattr(sys.modules[__name__], "configuration", lambda: reviewed)
    adapter = owned_target(tmp_path, monkeypatch)
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    try:
        runtime.target_profiles.control("register", reviewed.to_dict())
        handle = runtime.submit({"goal": "verify complete current browser value", "target": reviewed.name,
            "allowed_tools": list(reviewed.allowed_tools), "options": {"allowed_origins": ["https://allowed.test"]},
            "success_criteria": [{"kind": "browser", "operation": "value", "selector": "#field",
                                  "value": "reviewed"}]})
        for tool, arguments in [("AC_browser_navigate", {"url": "https://allowed.test/form"}),
                                ("AC_browser_fill", {"selector": "#field", "value": "reviewed"})]:
            observed = runtime.observe(handle.task_id)
            runtime.act(handle.task_id, {"tool": tool, "arguments": arguments,
                                        "observation_id": observed.observation_id})
        result = runtime.finish(handle.task_id)
        assert result.state == "succeeded", result.reason
        assert result.verification[0]["status"] == "passed"
        assert len(runtime.store.actions(handle.task_id)) == 2
        assert adapter._channel is None
    finally:
        runtime.close()


def test_real_sdk_rooted_transfers_keep_cookie_and_bytes_inside_owned_helper(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import hashlib
    import threading
    from je_auto_control.utils.agent_runtime import draft_agent_workflow
    records = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            records.append((self.path, dict(self.headers)))
            self.send_response(200)
            self.send_header("Content-Length", "6")
            self.end_headers()
            self.wfile.write(b"report")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    reviewed = AgentTargetProfile(name="reviewed-browser", kind="browser", roots=(str(tmp_path),),
        allowed_tools=("AC_browser_navigate", "AC_browser_link", "AC_browser_download", "AC_workflow_manifest",
                       "AC_browser_upload"), settings={"allowed_origins": [origin]})
    monkeypatch.setattr(sys.modules[__name__], "configuration", lambda: reviewed)
    adapter = owned_target(tmp_path, monkeypatch, transfers=True)
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    try:
        runtime.target_profiles.control("register", reviewed.to_dict())
        draft = draft_agent_workflow("download_archive", {"backend": "browser", "roots": [str(tmp_path)],
            "directory": str(tmp_path / "archive"), "url": origin + "/query", "allowed_origins": [origin],
            "files": [{"name": "report.bin", "selector": "#download"}]})
        draft["allowed_tools"].append("AC_browser_upload")
        draft["actions"].insert(-1, {"tool": "AC_browser_upload", "arguments": {
            "selector": "#upload", "path": str(tmp_path / "archive" / "report.bin"),
            "sha256": hashlib.sha256(b"report").hexdigest()}})
        handle = runtime.submit(draft)
        result = run_task(runtime, handle.task_id)
        assert result.state == "succeeded", result.reason
        assert records[0][0] == "/file"
        assert "Proxy-Authorization" not in records[0][1]
        assert (tmp_path / "archive" / "report.bin").read_bytes() == b"report"
        assert adapter._channel is None
        assert adapter._resource is None
        assert_real_sdk_download_cancellation(tmp_path, origin)
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def assert_real_sdk_download_cancellation(root, origin):
    """Foreign SDK containment must preserve the host's cancellation while closing the owned response."""
    from concurrent.futures import CancelledError
    from unittest.mock import patch
    from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    spec = AgentTaskSpec.from_dict({"goal": "cancelled download", "target": "reviewed-browser",
        "roots": [str(root)], "allowed_tools": ["AC_browser_navigate", "AC_browser_download"],
        "options": {"allowed_origins": [origin]}, "success_criteria": [{"kind": "actions_complete"}]})

    def checkpoint():
        if list(root.glob(".agent-*.part")):
            raise CancelledError()

    target = BrowserTarget()
    try:
        with patch("je_web_runner.webdriver.playwright_wrapper._require_playwright", return_value=fake_runtime()):
            target.ready(spec)
        with operation_scope(TaskOperation(spec, checkpoint, None)):
            target.perform("AC_browser_navigate", {"url": origin + "/query"})
            with pytest.raises(CancelledError):
                target.perform("AC_browser_download", {"url": origin + "/file", "directory": str(root),
                                                       "name": "cancelled.bin"})
        assert not (root / "cancelled.bin").exists()
        assert not list(root.glob(".agent-*.part"))
    finally:
        target.cleanup()
