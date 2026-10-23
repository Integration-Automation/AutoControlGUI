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


def fake_runtime(*, hang=False):
    """The real SDK lifecycle sees an event-capable fake page; no engine API is imported."""
    state = {"value": "", "url": "about:blank"}
    events = {}
    page, context, browser, runtime, factory = (MagicMock() for _index in range(5))
    del page.execute_script  # Match Playwright's interface; do not accidentally select Selenium dispatch.
    context.on.side_effect = lambda name, callback: events.setdefault(name, []).append(callback)

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
    element.evaluate.side_effect = lambda *_args: state["value"]
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


def owned_target(tmp_path, monkeypatch, *, hang=False):
    from je_auto_control.utils.agent_runtime import target_profiles
    script = (
        "import sys; sys.path.insert(0,sys.argv[1]); "
        "from headless.test_agent_browser_webrunner_contract import fake_runtime; "
        "from je_web_runner.webdriver import playwright_wrapper as module; "
        f"module._require_playwright=lambda:fake_runtime(hang={hang!r}); "
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
