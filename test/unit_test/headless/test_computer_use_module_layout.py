"""The computer-use backend was split by request shape; its names did not move.

``anthropic_computer_use.py`` was 27 lines from the file-length limit. The
action translation, the message blocks, the beta tool path and the toolset
path now have a module each, and every name that was imported from
``anthropic_computer_use`` -- by callers and by the tests of its behaviour --
is still importable from there and is the same object.
"""
from je_auto_control.utils.agent import backends
from je_auto_control.utils.agent.backends import (
    _computer_actions, _computer_beta_path, _computer_messages, _computer_toolset_path,
    anthropic_computer_use as cu,
)

#: name -> the module that now defines it.
_MOVED = {
    "_decision_from_computer_action": _computer_actions,
    "_scroll_decision": _computer_actions,
    "_hold_key_decision": _computer_actions,
    "_action_wait": _computer_actions,
    "_clamp_decision": _computer_actions,
    "_parse_combo": _computer_actions,
    "_normalise_key": _computer_actions,
    "_ACTION_HANDLERS": _computer_actions,
    "_CLICK_ACTIONS": _computer_actions,
    "_MAX_WAIT_S": _computer_actions,
    "_MAX_SCROLL_NOTCHES": _computer_actions,
    "_MAX_KEY_REPEAT": _computer_actions,
    "_tool_result_content": _computer_messages,
    "_initial_user_content": _computer_messages,
    "_TOOL_BETAS": _computer_beta_path,
    "_DEFAULT_TOOL_TYPE": _computer_beta_path,
}


def test_every_moved_name_is_still_importable_from_the_backend_module():
    for name, home in _MOVED.items():
        assert getattr(cu, name) is getattr(home, name), name


def test_the_public_name_is_unchanged():
    assert cu.__all__ == ["ComputerUseAgentBackend"]
    assert backends.ComputerUseAgentBackend is cu.ComputerUseAgentBackend
    assert cu.ComputerUseAgentBackend.__module__ == cu.__name__


def test_the_backend_is_both_paths():
    backend = cu.ComputerUseAgentBackend
    assert issubclass(backend, _computer_beta_path.BetaToolPath)
    assert issubclass(backend, _computer_toolset_path.ToolsetPath)
    for method in ("decide_next_action", "_handle_response", "_pending_result",
                   "_handle_toolset_response", "_toolset_decision", "_zoom_decision",
                   "_fit", "_toolset_result_content", "_decide_with_toolset"):
        assert callable(getattr(backend, method)), method


def test_default_tool_and_betas_are_what_they_were():
    assert cu._DEFAULT_MODEL == "claude-opus-5"
    assert cu._DEFAULT_TOOL_TYPE == "computer_20251124"
    assert cu._TOOL_BETAS == {"computer_20250124": "computer-use-2025-01-24",
                              "computer_20251124": "computer-use-2025-11-24"}
