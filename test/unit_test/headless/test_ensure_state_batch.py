"""Headless tests for ensure_state (injected reader / setter / toggle)."""
import je_auto_control as ac
from je_auto_control.utils.ensure_state import ensure_state, ensure_toggle


class Cell:
    """A tiny mutable state holder for reader / setter seams."""

    def __init__(self, value):
        self.value = value
        self.sets = 0

    def read(self):
        return self.value

    def write(self, new):
        self.sets += 1
        self.value = new


# --- ensure_state ---------------------------------------------------------

def test_ensure_state_noop_when_already_matches():
    cell = Cell("on")
    result = ensure_state("on", reader=cell.read, setter=cell.write)
    assert result == {"ok": True, "changed": False, "value": "on",
                      "attempts": 0}
    assert cell.sets == 0  # idempotent: setter never called


def test_ensure_state_sets_when_different():
    cell = Cell("off")
    result = ensure_state("on", reader=cell.read, setter=cell.write)
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["value"] == "on"
    assert result["attempts"] == 1
    assert cell.sets == 1


def test_ensure_state_gives_up_when_setter_ineffective():
    # setter that never actually changes the value
    reads = {"n": 0}

    def stubborn_set(_value):
        reads["n"] += 1

    result = ensure_state("on", reader=lambda: "off", setter=stubborn_set,
                          attempts=3)
    assert result["ok"] is False
    assert result["changed"] is True
    assert result["attempts"] == 3
    assert reads["n"] == 3


def test_ensure_state_custom_equals():
    cell = Cell("ON")
    # case-insensitive equality means "on" already matches "ON"
    result = ensure_state("on", reader=cell.read, setter=cell.write,
                          equals=lambda a, b: a.lower() == b.lower())
    assert result["changed"] is False
    assert cell.sets == 0


# --- ensure_toggle --------------------------------------------------------

def test_ensure_toggle_noop_when_already_desired():
    state = {"on": True}
    flips = {"n": 0}

    def toggle():
        flips["n"] += 1
        state["on"] = not state["on"]

    result = ensure_toggle(True, is_on=lambda: state["on"], toggle=toggle)
    assert result["changed"] is False
    assert flips["n"] == 0


def test_ensure_toggle_flips_once_to_reach_desired():
    state = {"on": False}
    flips = {"n": 0}

    def toggle():
        flips["n"] += 1
        state["on"] = not state["on"]

    result = ensure_toggle(True, is_on=lambda: state["on"], toggle=toggle)
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["value"] is True
    assert flips["n"] == 1


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_ensure_field_value" in known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_ensure_field_value" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_ensure_field_value" in specs


def test_facade_exports():
    for name in ("ensure_state", "ensure_toggle"):
        assert hasattr(ac, name) and name in ac.__all__
