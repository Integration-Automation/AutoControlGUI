"""Headless tests for Otsu auto-thresholded template matching."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.match_autothresh import (  # noqa: E402
    auto_threshold, match_auto,
)


def _template():
    tmpl = np.zeros((24, 24), dtype=np.uint8)
    tmpl[:, :12] = 200
    return tmpl


def _haystack(*tops_lefts):
    hay = np.zeros((160, 220), dtype=np.uint8)
    tmpl = _template()
    for top, left in tops_lefts:
        hay[top:top + 24, left:left + 24] = tmpl
    return hay


def test_auto_threshold_reports_metrics():
    info = auto_threshold(_template(), haystack=_haystack((20, 30), (20, 150)))
    assert set(info) == {"threshold", "separability", "n_above"}
    assert 0.0 < info["threshold"] < 1.0
    assert info["separability"] > 0.3   # clearly bimodal: matches vs background


def test_match_auto_finds_both_occurrences():
    matches = match_auto(_template(), haystack=_haystack((20, 30), (20, 150)),
                         floor=0.5)
    assert len(matches) == 2
    xs = sorted(m.x for m in matches)
    assert abs(xs[0] - 30) <= 1 and abs(xs[1] - 150) <= 1


def test_floor_prevents_noise_on_blank():
    # a blank haystack has no bimodal split; floor keeps it from matching noise
    matches = match_auto(_template(), haystack=np.zeros((160, 220), np.uint8),
                         floor=0.6)
    assert matches == []


def test_blank_separability_is_low():
    info = auto_threshold(_template(), haystack=np.zeros((160, 220), np.uint8))
    assert info["separability"] < 0.3   # unimodal → do not trust the threshold


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_match_auto", "AC_auto_threshold"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_auto", "ac_auto_threshold"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_match_auto", "AC_auto_threshold"} <= specs


def test_facade_exports():
    for name in ("match_auto", "auto_threshold"):
        assert hasattr(ac, name) and name in ac.__all__
