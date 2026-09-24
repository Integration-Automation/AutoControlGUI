"""Computer-use backend defects from the 2026-09-24 audit (fake client only).

The ``computer`` tool went through the plain ``messages.create`` with no beta,
so the real API rejected every request; the model's scroll amount and
wait / hold durations were unbounded (a huge scroll overflowed the platform
call, a long wait ran past the run's time budget); and a scroll ignored the
model's coordinate.
"""
import pytest

from je_auto_control.utils.agent.backends import anthropic_computer_use as cu
from je_auto_control.utils.agent.backends.base import AgentBackendError


def test_an_unknown_tool_version_needs_an_explicit_beta():
    with pytest.raises(AgentBackendError, match="beta"):
        cu.ComputerUseAgentBackend(display_width_px=800, display_height_px=600,
                                   client=object(), tool_type="computer_29990101")
    cu.ComputerUseAgentBackend(display_width_px=800, display_height_px=600, client=object(),
                               tool_type="computer_29990101", beta="computer-use-2999-01-01")


def test_the_older_tool_version_keeps_its_own_beta():
    backend = cu.ComputerUseAgentBackend(display_width_px=800, display_height_px=600,
                                         client=object(), tool_type="computer_20250124")
    assert backend._beta == "computer-use-2025-01-24"


def test_a_huge_scroll_is_bounded_and_goes_where_the_model_pointed():
    decision = cu._scroll_decision({"scroll_direction": "down", "scroll_amount": 10 ** 12,
                                    "coordinate": [5, 7]})
    assert decision["input"] == {"scroll_value": -cu._MAX_SCROLL_NOTCHES, "x": 5, "y": 7}


@pytest.mark.parametrize("duration", [10 ** 9, -5])
def test_waits_and_holds_are_bounded(duration):
    wait = cu._action_wait({"duration": duration})
    seconds = wait["input"]["action_list"][0][1]["seconds"]
    assert 0 <= seconds <= cu._MAX_WAIT_S
    hold = cu._hold_key_decision({"text": "a", "duration": duration})
    assert 0 <= hold["input"]["duration_s"] <= cu._MAX_WAIT_S
