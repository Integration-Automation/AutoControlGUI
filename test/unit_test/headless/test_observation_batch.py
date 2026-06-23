"""Headless tests for the indexed a11y text observation. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.observation import (
    flatten_tree, observation_index, serialize_observation,
)


def _tree():
    return [{"role": "window", "name": "App", "children": [
        {"role": "button", "name": "Save", "x": 10, "y": 10, "width": 40,
         "height": 20},
        {"role": "textbox", "name": "Search", "x": 100, "y": 10, "width": 80,
         "height": 20},
        {"role": "label", "name": "static", "x": 10, "y": 50, "width": 60,
         "height": 20},
        {"role": "button", "name": "Offscreen", "x": 10, "y": 5000, "width": 40,
         "height": 20},
    ]}]


def test_flatten_keeps_only_interactive():
    roles = [(e["role"], e["name"]) for e in flatten_tree(_tree())]
    assert ("button", "Save") in roles and ("textbox", "Search") in roles
    assert ("label", "static") not in roles      # non-interactive dropped
    assert ("window", "App") not in roles


def test_flatten_all_when_not_interactive_only():
    roles = {e["role"] for e in flatten_tree(_tree(), interactive_only=False)}
    assert {"window", "button", "textbox", "label"} <= roles


def test_observation_index_clips_viewport_and_indexes():
    indexed = observation_index(_tree(), viewport=(0, 0, 1920, 1080))
    assert [(e["index"], e["name"]) for e in indexed] == [(0, "Save"),
                                                          (1, "Search")]
    # the y=5000 button is clipped out


def test_observation_index_cap():
    assert len(observation_index(_tree(), max_elements=1)) == 1


def test_serialize_observation_lines():
    text = serialize_observation(_tree(), viewport=(0, 0, 1920, 1080))
    assert text.splitlines() == ['[0] button "Save" @(30,20)',
                                 '[1] textbox "Search" @(140,20)']


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_serialize_observation", "AC_observation_index"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_serialize_observation", "ac_observation_index"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_serialize_observation", "AC_observation_index"} <= specs


def test_facade_exports():
    for attr in ("flatten_tree", "observation_index", "serialize_observation"):
        assert hasattr(ac, attr) and attr in ac.__all__
