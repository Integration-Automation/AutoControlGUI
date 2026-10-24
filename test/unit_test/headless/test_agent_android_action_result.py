"""Closed phase/exit matching never turns missing output or a post-input failure into no effect."""
from dataclasses import FrozenInstanceError

import pytest

from je_auto_control.utils.agent_runtime.android_action_result import (
    ACTION_ATTEMPTED, ACTION_HEADER, ACTION_MARKER, ACTION_RETURNED, parse_android_action_result)
from je_auto_control.utils.agent_runtime.android_transport import AdbShellResult
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@pytest.mark.parametrize("code", [91, 92, 93, 95])
def test_only_complete_pre_input_refusal_proves_no_input_invocation(code):
    result = parse_android_action_result(AdbShellResult(ACTION_HEADER + f"refused:{code}\n".encode(), b"", code))
    assert result.phase == "pre_input_refused"
    assert not result.may_have_effect
    with pytest.raises(FrozenInstanceError):
        result.phase = "input_returned"


@pytest.mark.parametrize("code", [91, 92, 93])
def test_same_exit_after_input_does_not_certify_no_effect(code):
    result = parse_android_action_result(AdbShellResult(ACTION_RETURNED + f"post_refused:{code}\n".encode(), b"", code))
    assert result.phase == "post_input_refused"
    assert result.may_have_effect


@pytest.mark.parametrize("stdout,code,phase", [
    (ACTION_MARKER, 0, "input_returned"),
    (ACTION_ATTEMPTED + b"input_failed\n", 94, "input_failed"),
])
def test_returned_input_and_partial_failure_keep_possible_effects(stdout, code, phase):
    result = parse_android_action_result(AdbShellResult(stdout, b"", code))
    assert result.phase == phase
    assert result.may_have_effect
    assert not hasattr(result, "input_idle")


@pytest.mark.parametrize("stdout", [
    b"", b"__JE_ANDROID_ACTION_V1__\n", ACTION_HEADER, ACTION_ATTEMPTED, ACTION_RETURNED,
    ACTION_MARKER[:-1], ACTION_MARKER + b"extra", ACTION_MARKER * 2,
    ACTION_HEADER + b"refused:091\n", ACTION_HEADER + b"refused:94\n",
    ACTION_HEADER + b"refused:95\n" + b"attempted\n", ACTION_HEADER + b"post_refused:93\n",
    ACTION_RETURNED + b"post_refused:95\n", ACTION_HEADER + b"verified\n",
    ACTION_HEADER + b"attempted\nrefused:93\n", b"private-device-diagnostic\xff",
])
@pytest.mark.parametrize("code", [0, 91, 93, 94, 95, 96])
def test_partial_forged_extra_or_legacy_output_remains_unknown(stdout, code):
    with pytest.raises(AgentTaskError, match="unknown") as error:
        parse_android_action_result(AdbShellResult(stdout, b"", code))
    assert "private-device-diagnostic" not in str(error.value)


@pytest.mark.parametrize("code", [0, 91, 92, 94, 95, True, False, 93.0, "93"])
def test_pre_refusal_with_wrong_exit_type_or_value_is_unknown(code):
    with pytest.raises(AgentTaskError, match="unknown"):
        parse_android_action_result(AdbShellResult(ACTION_HEADER + b"refused:93\n", b"", code))


@pytest.mark.parametrize("result", [
    None, {}, AdbShellResult(ACTION_MARKER, b"private-password", 0),
    AdbShellResult(ACTION_MARKER, "", 0), AdbShellResult("not-bytes", b"", 0),
])
def test_untrusted_diagnostics_and_invalid_transport_objects_are_withheld(result):
    with pytest.raises(AgentTaskError, match="unknown") as error:
        parse_android_action_result(result)
    assert "private-password" not in str(error.value)
