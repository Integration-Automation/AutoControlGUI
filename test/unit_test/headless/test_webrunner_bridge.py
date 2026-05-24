"""Phase 7.7: WebRunner bridge tests."""
from unittest.mock import MagicMock, patch

import pytest

from je_auto_control.utils.webrunner_bridge import (
    WebRunnerBridgeError, is_webrunner_available, list_webrunner_commands,
    run_webrunner_action, run_webrunner_actions,
)


# --- availability check ----------------------------------------------

def test_is_available_returns_bool():
    assert is_webrunner_available() in (True, False)


def test_is_available_false_when_import_fails():
    with patch.dict("sys.modules", {"je_web_runner": None}):
        # patch.dict with None forces ImportError on import
        assert is_webrunner_available() is False


# --- run_webrunner_action --------------------------------------------

def _fake_executor(commands):
    """Build a fake executor whose event_dict holds the given callables."""
    mock = MagicMock()
    mock.event_dict = commands
    return mock


def test_run_action_dispatches_through_webrunner_executor():
    seen = {}

    def fake_get_url(url=None):
        seen["url"] = url
        return {"ok": True}

    fake_exec = _fake_executor({"WR_get_url": fake_get_url})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        result = run_webrunner_action(
            {"action": "WR_get_url",
             "params": {"url": "https://example.com"}},
        )
    assert result == {"ok": True}
    assert seen["url"] == "https://example.com"


def test_run_action_accepts_missing_params():
    """``params`` is optional; defaults to an empty dict."""
    fake = MagicMock(return_value="done")
    fake_exec = _fake_executor({"WR_quit": fake})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        assert run_webrunner_action({"action": "WR_quit"}) == "done"
    fake.assert_called_once_with()


@pytest.mark.parametrize("bad_input", [
    None,
    [],
    "not-a-mapping",
])
def test_run_action_rejects_non_mapping(bad_input):
    with pytest.raises(WebRunnerBridgeError):
        run_webrunner_action(bad_input)


@pytest.mark.parametrize("bad_name", ["", "AC_click_mouse", "go_to_url"])
def test_run_action_requires_wr_prefix(bad_name):
    with pytest.raises(WebRunnerBridgeError, match="WR_"):
        run_webrunner_action({"action": bad_name})


def test_run_action_unknown_command_raises():
    fake_exec = _fake_executor({})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        with pytest.raises(WebRunnerBridgeError, match="unknown"):
            run_webrunner_action({"action": "WR_definitely_not_real"})


def test_run_action_translates_typeerror_to_bridge_error():
    """WR command rejecting kwargs surfaces as WebRunnerBridgeError."""

    def strict(must_have: int):
        return must_have

    fake_exec = _fake_executor({"WR_strict": strict})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        with pytest.raises(WebRunnerBridgeError, match="rejected params"):
            run_webrunner_action({"action": "WR_strict",
                                  "params": {"wrong_key": 1}})


def test_run_action_params_must_be_mapping():
    fake_exec = _fake_executor({"WR_x": lambda **_kw: None})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        with pytest.raises(WebRunnerBridgeError, match="'params'"):
            run_webrunner_action({"action": "WR_x", "params": "string"})


# --- run_webrunner_actions ------------------------------------------

def test_run_actions_chains_through_each_in_order():
    seen = []

    def make(name):
        def fn(value=None):
            seen.append((name, value))
            return name
        return fn

    fake_exec = _fake_executor({
        "WR_one": make("one"), "WR_two": make("two"),
    })
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        results = run_webrunner_actions([
            {"action": "WR_one", "params": {"value": 1}},
            {"action": "WR_two", "params": {"value": 2}},
        ])
    assert results == ["one", "two"]
    assert seen == [("one", 1), ("two", 2)]


def test_run_actions_stops_at_first_error():
    seen = []
    fake_exec = _fake_executor({
        "WR_first": lambda: seen.append("first") or "ok",
    })
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        with pytest.raises(WebRunnerBridgeError):
            run_webrunner_actions([
                {"action": "WR_first"},
                {"action": "WR_second"},  # not in event_dict
            ])
    # First WR ran, second never started.
    assert seen == ["first"]


def test_run_actions_rejects_non_list():
    with pytest.raises(WebRunnerBridgeError):
        run_webrunner_actions("not-a-list")  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test


# --- list_webrunner_commands ----------------------------------------

def test_list_commands_filters_to_wr_prefix():
    fake_exec = _fake_executor({
        "WR_one": lambda: None, "WR_two": lambda: None,
        "AC_ignore": lambda: None, 42: lambda: None,
    })
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        cmds = list_webrunner_commands()
    assert cmds == ["WR_one", "WR_two"]


# --- AC_web_* dispatch ---------------------------------------------

def test_ac_web_available_returns_bool():
    """AC_web_available should call through to is_webrunner_available."""
    from je_auto_control.utils.executor.action_executor import executor
    fn = executor.event_dict["AC_web_available"]
    assert fn() in (True, False)


def test_ac_web_run_dispatches_to_bridge():
    from je_auto_control.utils.executor.action_executor import executor
    ac_web_run = executor.event_dict["AC_web_run"]
    fake = MagicMock(return_value={"done": True})
    fake_exec = _fake_executor({"WR_quit": fake})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        assert ac_web_run(
            {"action": "WR_quit", "params": {}},
        ) == {"done": True}
    fake.assert_called_once_with()


# --- convenience helpers --------------------------------------------

def test_web_open_runs_driver_then_navigate():
    from je_auto_control.utils.webrunner_bridge import web_open
    calls = []

    def driver(**params):
        calls.append(("driver", params))
        return "driver-ok"

    def to_url(**params):
        calls.append(("to_url", params))
        return "nav-ok"

    fake_exec = _fake_executor({
        "WR_get_webdriver_manager": driver,
        "WR_to_url": to_url,
    })
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        result = web_open("https://example.com", browser="firefox")
    assert result == "nav-ok"
    assert calls[0] == ("driver", {"webdriver_name": "firefox"})
    assert calls[1] == ("to_url", {"url": "https://example.com"})


def test_web_open_rejects_blank_url():
    from je_auto_control.utils.webrunner_bridge import web_open
    with pytest.raises(WebRunnerBridgeError):
        web_open("   ")


def test_web_quit_invokes_wr_quit():
    from je_auto_control.utils.webrunner_bridge import web_quit
    quit_fn = MagicMock(return_value=True)
    fake_exec = _fake_executor({"WR_quit": quit_fn})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        assert web_quit() is True
    quit_fn.assert_called_once_with()


def test_web_screenshot_passes_file_name():
    from je_auto_control.utils.webrunner_bridge import web_screenshot
    seen = {}

    def shot(file_name=None):
        seen["file_name"] = file_name
        return file_name

    fake_exec = _fake_executor({"WR_save_screenshot": shot})
    with patch(
        "je_auto_control.utils.webrunner_bridge.bridge._executor",
        return_value=fake_exec,
    ):
        assert web_screenshot("out.png") == "out.png"
    assert seen["file_name"] == "out.png"


def test_web_screenshot_rejects_blank_path():
    from je_auto_control.utils.webrunner_bridge import web_screenshot
    with pytest.raises(WebRunnerBridgeError):
        web_screenshot("")


def test_executor_registers_new_web_commands():
    from je_auto_control.utils.executor.action_executor import executor
    commands = executor.known_commands()
    assert {
        "AC_web_open", "AC_web_quit", "AC_web_screenshot",
        "AC_web_current_url",
    } <= commands


def test_mcp_factory_registers_web_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_web_available", "ac_web_list_commands", "ac_web_run",
        "ac_web_run_actions", "ac_web_open", "ac_web_quit",
        "ac_web_screenshot", "ac_web_current_url",
    } <= names


def test_facade_exports_webrunner_bridge():
    import je_auto_control as ac
    for name in ("is_webrunner_available", "run_webrunner_action",
                  "web_open", "web_quit", "web_screenshot",
                  "web_current_url", "WebRunnerBridgeError"):
        assert hasattr(ac, name), f"missing facade export: {name}"
