"""Headless tests for ime_state (injected reader / clock)."""
import sys

import je_auto_control as ac
from je_auto_control.utils.ime_state import (
    decode_conversion_mode, ime_state, is_composing,
    wait_for_composition_commit,
)
from je_auto_control.utils.ime_state.ime_state import (
    IME_CMODE_FULLSHAPE, IME_CMODE_NATIVE, IME_CMODE_ROMAN,
)


# --- pure conversion-mode decode ------------------------------------------

def test_decode_conversion_mode_native_roman():
    flags = IME_CMODE_NATIVE | IME_CMODE_ROMAN
    decoded = decode_conversion_mode(flags)
    assert decoded["native"] is True
    assert decoded["roman"] is True
    assert decoded["full_shape"] is False
    assert decoded["katakana"] is False


def test_decode_conversion_mode_zero_all_false():
    decoded = decode_conversion_mode(0)
    assert decoded == {"native": False, "katakana": False, "full_shape": False,
                       "roman": False, "char_code": False}


# --- state via injected reader --------------------------------------------

def test_ime_state_composing():
    state = ime_state(reader=lambda: {"open": True,
                                      "conversion": IME_CMODE_NATIVE,
                                      "composition": "あ"})
    assert state["open"] is True
    assert state["composing"] is True
    assert state["composition"] == "あ"
    assert state["conversion"]["native"] is True
    assert state["conversion_flags"] == IME_CMODE_NATIVE


def test_ime_state_idle_not_composing():
    state = ime_state(
        reader=lambda: {"open": False, "conversion": 0, "composition": ""})
    assert state["composing"] is False
    assert state["composition"] == ""


def test_ime_state_tolerates_missing_keys():
    state = ime_state(reader=dict)  # empty dict
    assert state["open"] is False
    assert state["composing"] is False
    assert state["conversion_flags"] == 0


def test_is_composing_reflects_reader():
    assert is_composing(
        reader=lambda: {"composition": "한", "conversion": 0,
                        "open": True}) is True
    assert is_composing(
        reader=lambda: {"composition": "", "conversion": 0,
                        "open": True}) is False


# --- wait for commit ------------------------------------------------------

def _reader_sequence(compositions):
    state = {"i": 0}

    def reader():
        i = min(state["i"], len(compositions) - 1)
        state["i"] += 1
        return {"open": True, "conversion": 0, "composition": compositions[i]}

    return reader


def test_wait_for_composition_commit_returns_true():
    reader = _reader_sequence(["typ", "typi", ""])  # commits on 3rd read
    clock = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    ok = wait_for_composition_commit(reader=reader, timeout_s=10.0,
                                     interval_s=1.0,
                                     clock=lambda: next(clock),
                                     sleep=lambda _s: None)
    assert ok is True


def test_wait_for_composition_commit_times_out():
    reader = _reader_sequence(["forever"])  # never commits
    times = iter([0.0, 0.0, 5.0, 10.0])
    ok = wait_for_composition_commit(reader=reader, timeout_s=5.0,
                                     interval_s=1.0,
                                     clock=lambda: next(times),
                                     sleep=lambda _s: None)
    assert ok is False


# --- wiring ---------------------------------------------------------------

def test_executor_pure_decode_path():
    from je_auto_control.utils.executor.action_executor import (
        _decode_conversion_mode,
    )
    assert _decode_conversion_mode(IME_CMODE_FULLSHAPE)["full_shape"] is True


def test_default_reader_raises_off_windows():
    from je_auto_control.utils.ime_state.ime_state import _default_reader
    if not sys.platform.startswith("win"):
        try:
            _default_reader()
            raised = False
        except RuntimeError:
            raised = True
        assert raised is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_ime_state", "AC_is_composing",
            "AC_wait_for_composition_commit",
            "AC_decode_conversion_mode"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_ime_state", "ac_is_composing",
            "ac_wait_for_composition_commit",
            "ac_decode_conversion_mode"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_ime_state", "AC_is_composing",
            "AC_wait_for_composition_commit",
            "AC_decode_conversion_mode"} <= specs


def test_facade_exports():
    for name in ("ime_state", "is_composing", "wait_for_composition_commit",
                 "decode_conversion_mode"):
        assert hasattr(ac, name) and name in ac.__all__
