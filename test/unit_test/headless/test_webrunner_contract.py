"""The WebRunner bridge against the real ``je_web_runner`` package (skipped where it is not installed).

The other bridge tests use a fake executor, so they cannot see WebRunner move or rename
what the bridge relies on (WebRunner's ``architecture.md`` §6): the module path of
``executor`` and ``execute_one``, the ``WR_*`` names the convenience helpers send, and a
failing command reaching AutoControl as ``WebRunnerBridgeError``.
"""
import importlib
import importlib.util

import pytest

from je_auto_control.utils.webrunner_bridge import (
    WebRunnerBridgeError, is_webrunner_available, list_webrunner_commands,
    run_webrunner_action,
)

pytestmark = pytest.mark.skipif(importlib.util.find_spec("je_web_runner") is None,
                                reason="je_web_runner is not installed")

_SENT_BY_THE_HELPERS = ("WR_get_webdriver_manager", "WR_to_url", "WR_quit",
                        "WR_save_screenshot", "WR_get_current_url")


@pytest.fixture(scope="module")
def webrunner_executor(tmp_path_factory):
    """Import WebRunner from a scratch cwd: its import opens ``WEBRunner.log`` in the cwd."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path_factory.mktemp("webrunner_cwd"))
    try:
        yield importlib.import_module("je_web_runner.utils.executor.action_executor")
    finally:
        monkeypatch.undo()


def test_the_helpers_commands_are_registered(webrunner_executor):
    registered = set(list_webrunner_commands())
    assert set(_SENT_BY_THE_HELPERS) <= registered
    assert registered <= set(webrunner_executor.executor.event_dict)
    assert is_webrunner_available() is True


def test_execute_one_is_where_the_bridge_looks(webrunner_executor):
    assert callable(webrunner_executor.execute_one)


def test_a_failing_command_arrives_as_a_bridge_error(webrunner_executor):
    # No browser is running, so the wait fails inside WebRunner.
    with pytest.raises(WebRunnerBridgeError, match="WR_wait_for_url"):
        run_webrunner_action({"action": "WR_wait_for_url", "params": {"pattern": "never", "timeout": 0.1}})
