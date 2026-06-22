"""Headless tests for the visual-regression action wiring.

PIL images are passed directly (no real screen); the AC_/MCP paths
monkeypatch the screen grab so they stay deterministic and offline.
"""
import pytest
from PIL import Image

import je_auto_control as ac
from je_auto_control.utils.visual_regression import compare as vr


def _img(color, size=(8, 8)):
    return Image.new("RGB", size, color)


def test_take_golden_and_match(tmp_path):
    golden = tmp_path / "g.png"
    ac.take_golden(str(golden), source=_img((10, 20, 30)))
    assert golden.exists()
    result = ac.compare_to_golden(str(golden), actual=_img((10, 20, 30)))
    assert result.matched is True
    assert result.diff_pct == pytest.approx(0.0)


def test_mismatch_reports_diff(tmp_path):
    golden = tmp_path / "g.png"
    ac.take_golden(str(golden), source=_img((0, 0, 0)))
    result = ac.compare_to_golden(str(golden), actual=_img((255, 255, 255)))
    assert result.matched is False
    assert result.diff_pct == pytest.approx(100.0)
    assert result.diff_image is not None


def test_tolerance_allows_small_diff(tmp_path):
    golden = tmp_path / "g.png"
    base = _img((0, 0, 0), size=(10, 10))
    ac.take_golden(str(golden), source=base)
    changed = base.copy()
    changed.putpixel((0, 0), (255, 255, 255))  # 1 / 100 px = 1%
    assert ac.compare_to_golden(str(golden), actual=changed,
                                tolerance=2.0).matched is True
    assert ac.compare_to_golden(str(golden), actual=changed,
                                tolerance=0.0).matched is False


def test_ac_assert_visual_first_run_creates_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "_grab", lambda region: _img((5, 5, 5)))
    golden = tmp_path / "screen.png"
    record = ac.execute_action(
        [["AC_assert_visual", {"golden_path": str(golden)}]])
    assert golden.exists()
    assert any("created" in str(v) for v in record.values())


def test_ac_assert_visual_passes_then_fails(tmp_path, monkeypatch):
    from je_auto_control.utils.exception.exceptions import (
        AutoControlAssertionException,
    )
    golden = tmp_path / "screen.png"
    monkeypatch.setattr(vr, "_grab", lambda region: _img((5, 5, 5)))
    ac.take_golden(str(golden), source=_img((5, 5, 5)))
    # same screen -> matches
    rec_ok = ac.execute_action(
        [["AC_assert_visual", {"golden_path": str(golden)}]])
    assert any("'matched': True" in str(v) for v in rec_ok.values())
    # different screen -> assertion raises (like every other AC_assert_*)
    monkeypatch.setattr(vr, "_grab", lambda region: _img((200, 0, 0)))
    with pytest.raises(AutoControlAssertionException):
        ac.execute_action([["AC_assert_visual", {"golden_path": str(golden)}]])
    # raise_on_fail=False returns a dict instead of raising
    rec_soft = ac.execute_action(
        [["AC_assert_visual", {"golden_path": str(golden),
                               "raise_on_fail": False}]])
    assert any("'matched': False" in str(v) for v in rec_soft.values())


def test_ac_take_golden_command(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "_grab", lambda region: _img((1, 2, 3)))
    golden = tmp_path / "out.png"
    ac.execute_action([["AC_take_golden", {"path": str(golden)}]])
    assert golden.exists()


def test_facade_and_mcp_wiring():
    assert "AC_take_golden" in ac.executor.known_commands()
    assert "AC_assert_visual" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_take_golden", "ac_assert_visual"} <= names
