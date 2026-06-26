"""Headless tests for act_with_mode (trial / force / auto over the gate)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.act_modes import ACT_MODES, act_with_mode
from je_auto_control.utils.actionability import GateConfig


def _gate_config():
    """A GateConfig whose clock advances so the gate can time out / poll."""
    ticks = iter([float(t) for t in range(0, 40)])
    return GateConfig(timeout_s=3.0, stable_for_s=0.0, poll_interval_s=1.0,
                      clock=lambda: next(ticks), sleep=lambda _s: None)


# --- force ----------------------------------------------------------------

def test_force_acts_without_any_checks():
    clicked = []
    # enabled_probe says disabled, but force ignores the gate entirely
    out = act_with_mode(clicked.append, lambda: (10, 20, 4, 4), mode="force",
                        enabled_probe=lambda: False)
    assert out["mode"] == "force"
    assert out["acted"] is True
    assert out["point"] == [12, 22]      # centre of (10,20,4,4)
    assert clicked == [[12, 22]]


def test_force_no_target_does_not_act():
    clicked = []
    out = act_with_mode(clicked.append, lambda: None, mode="force")
    assert out["acted"] is False
    assert clicked == []


# --- trial ----------------------------------------------------------------

def test_trial_reports_but_never_acts():
    clicked = []
    out = act_with_mode(clicked.append, lambda: (0, 0, 2, 2), mode="trial",
                        config=_gate_config())
    assert out["mode"] == "trial"
    assert out["acted"] is False         # dry run: gate ran, no action
    assert out["actionable"] is True
    assert clicked == []                 # never clicked


def test_trial_reports_not_actionable_without_acting():
    clicked = []
    out = act_with_mode(clicked.append, lambda: None, mode="trial",
                        config=_gate_config())   # no bbox -> not visible
    assert out["acted"] is False
    assert out["actionable"] is False
    assert out["reason"] == "not visible"
    assert clicked == []


# --- auto -----------------------------------------------------------------

def test_auto_acts_when_actionable():
    clicked = []
    out = act_with_mode(clicked.append, lambda: (5, 5, 2, 2), mode="auto",
                        config=_gate_config())
    assert out["acted"] is True
    assert clicked == [[6, 6]]           # centre of (5,5,2,2)


def test_auto_does_not_act_when_gate_times_out():
    clicked = []
    out = act_with_mode(clicked.append, lambda: None, mode="auto",
                        config=_gate_config())   # never visible -> timeout
    assert out["acted"] is False
    assert out["actionable"] is False
    assert clicked == []


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        act_with_mode(lambda p: None, lambda: (0, 0, 1, 1), mode="bogus")


def test_act_modes_constant():
    assert set(ACT_MODES) == {"auto", "trial", "force"}


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_act_with_mode" in known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_act_with_mode" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_act_with_mode" in specs


def test_facade_exports():
    assert hasattr(ac, "act_with_mode") and "act_with_mode" in ac.__all__
