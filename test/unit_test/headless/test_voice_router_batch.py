"""Headless tests for the voice-command router. Speech-to-text is out of scope:
the router takes recognized text and the action runner is injected, so routing
is fully tested without audio or any speech dependency. Pure stdlib, no Qt."""
import je_auto_control as ac
from je_auto_control.utils.voice import VoiceRouter, default_voice_router


def _recording_runner():
    ran = []
    return ran, (lambda actions: ran.append(actions) or {"ok": True})


def test_register_and_phrases():
    router = VoiceRouter()
    router.register("save file", [["AC_noop", {}]])
    router.register("close window", [["AC_noop", {}]])
    assert router.phrases() == ["save file", "close window"]


def test_register_replaces_same_phrase():
    router = VoiceRouter()
    router.register("go", [["A", {}]])
    router.register("go", [["B", {}]])
    assert len(router.phrases()) == 1
    assert router.match("go").actions == [["B", {}]]


def test_fuzzy_match_tolerates_noise():
    router = VoiceRouter(threshold=0.6)
    router.register("save file", [["AC_save", {}]])
    matched = router.match("save the file")
    assert matched is not None and matched.phrase == "save file"


def test_no_match_below_threshold():
    router = VoiceRouter(threshold=0.9)
    router.register("save file", [["AC_save", {}]])
    assert router.match("totally different") is None


def test_dispatch_runs_matched_actions():
    router = VoiceRouter(threshold=0.6)
    router.register("save file", [["AC_save", {}]])
    ran, runner = _recording_runner()
    outcome = router.dispatch("save the file", runner=runner)
    assert outcome["matched"] is True
    assert outcome["phrase"] == "save file"
    assert ran == [[["AC_save", {}]]]


def test_dispatch_no_match_runs_nothing():
    router = VoiceRouter(threshold=0.9)
    router.register("save file", [["AC_save", {}]])
    ran, runner = _recording_runner()
    outcome = router.dispatch("xyzzy", runner=runner)
    assert outcome["matched"] is False
    assert ran == []


def test_listen_once_uses_recognizer():
    router = VoiceRouter(threshold=0.6)
    router.register("open menu", [["AC_open", {}]])
    ran, runner = _recording_runner()
    outcome = router.listen_once(lambda: "open the menu", runner=runner)
    assert outcome["phrase"] == "open menu"
    assert len(ran) == 1


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    default_voice_router.clear()
    try:
        ac.execute_action([[
            "AC_voice_register",
            {"phrase": "list windows", "actions": [["AC_list_windows", {}]]},
        ]])
        rec = ac.execute_action([["AC_voice_list", {}]])
        phrases = next(v for v in rec.values() if isinstance(v, dict))["phrases"]
        assert "list windows" in phrases
        rec2 = ac.execute_action([
            ["AC_voice_dispatch", {"text": "list the windows"}],
        ])
        outcome = next(v for v in rec2.values() if isinstance(v, dict))
        assert outcome["matched"] is True
    finally:
        default_voice_router.clear()       # leave global state clean


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_voice_register", "AC_voice_dispatch", "AC_voice_list",
            "AC_voice_clear"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_voice_register", "ac_voice_dispatch", "ac_voice_list",
            "ac_voice_clear"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_voice_register", "AC_voice_dispatch", "AC_voice_list",
            "AC_voice_clear"} <= cmds


def test_facade_exports():
    for attr in ("VoiceRouter", "VoiceCommand", "default_voice_router"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
