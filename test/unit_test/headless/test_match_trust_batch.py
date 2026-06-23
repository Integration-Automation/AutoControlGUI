"""Headless tests for template-match trust scoring on synthetic arrays."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.match_trust import (  # noqa: E402
    match_with_trust, score_peaks,
)


def _template():
    tmpl = np.zeros((24, 24), dtype=np.uint8)
    tmpl[:, :12] = 200  # asymmetric so correlation has variance
    return tmpl


def _haystack(*tops_lefts):
    hay = np.zeros((160, 200), dtype=np.uint8)
    tmpl = _template()
    for top, left in tops_lefts:
        hay[top:top + 24, left:left + 24] = tmpl
    return hay


def test_single_occurrence_is_unambiguous():
    result = match_with_trust(_template(), haystack=_haystack((20, 30)),
                              min_score=0.8)
    assert result is not None
    assert result.is_ambiguous is False
    assert result.peak_ratio < 0.9
    assert abs(result.x - 30) <= 1 and abs(result.y - 20) <= 1


def test_duplicate_occurrence_is_ambiguous():
    # the same template twice → a near-equal second peak → flagged ambiguous
    result = match_with_trust(_template(), haystack=_haystack((20, 30), (20, 140)),
                              min_score=0.8)
    assert result is not None
    assert result.is_ambiguous is True
    assert result.peak_ratio >= 0.9
    assert result.second_score >= 0.9


def test_score_peaks_reports_metrics():
    peaks = score_peaks(_template(), haystack=_haystack((20, 30)))
    assert peaks is not None
    assert set(peaks) == {"best", "second", "peak_ratio", "psr", "ambiguous",
                          "location"}
    assert peaks["best"] >= 0.99
    assert peaks["ambiguous"] is False


def test_min_score_filters_out():
    assert match_with_trust(_template(), haystack=np.zeros((160, 200), np.uint8),
                            min_score=0.95) is None


def test_psr_present_for_real_peak():
    result = match_with_trust(_template(), haystack=_haystack((20, 30)),
                              min_score=0.8)
    assert result.psr is None or result.psr > 0


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_match_with_trust" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_match_with_trust" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_match_with_trust" in specs


def test_facade_exports():
    for name in ("match_with_trust", "score_peaks", "TrustedMatch"):
        assert hasattr(ac, name) and name in ac.__all__
