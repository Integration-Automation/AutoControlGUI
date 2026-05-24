"""Tests for the pytest plugin + Gherkin step definitions."""
from unittest.mock import MagicMock, patch

import pytest


def test_plugin_module_exposes_marker_registration():
    """``pytest_configure`` registers the ``autocontrol`` marker line."""
    from je_auto_control.utils.pytest_plugin import plugin

    captured = []

    class _Config:
        def addinivalue_line(self, name, value):
            captured.append((name, value))

    plugin.pytest_configure(_Config())
    assert any(line[0] == "markers"
               and "autocontrol" in line[1]
               for line in captured)


def test_keywords_module_exports_expected_helpers():
    from je_auto_control.utils.pytest_plugin import keywords
    for name in ("keyword_click_image", "keyword_type_text",
                  "keyword_press_key", "keyword_screen_size",
                  "keyword_screenshot", "keyword_wait_for_image",
                  "keyword_wait_for_text"):
        assert hasattr(keywords, name), f"missing keyword: {name}"


def test_keyword_screenshot_invokes_screen_helper(tmp_path):
    from je_auto_control.utils.pytest_plugin.keywords import (
        keyword_screenshot,
    )
    target = tmp_path / "shot.png"
    with patch(
        "je_auto_control.wrapper.auto_control_screen.screenshot",
    ) as mocked:
        result = keyword_screenshot(str(target))
    mocked.assert_called_once_with(file_path=str(target), screen_region=None)
    assert result == str(target)


def test_keyword_click_image_forwards_threshold(tmp_path):
    from je_auto_control.utils.pytest_plugin.keywords import (
        keyword_click_image,
    )
    with patch(
        "je_auto_control.wrapper.auto_control_image.locate_and_click",
        return_value=(50, 60),
    ) as mocked:
        coords = keyword_click_image("x.png", button="mouse_right",
                                       detect_threshold=0.85)
    mocked.assert_called_once_with(
        "x.png", mouse_keycode="mouse_right", detect_threshold=0.85,
    )
    assert coords == (50, 60)


def test_keyword_wait_for_image_returns_first_hit(monkeypatch):
    from je_auto_control.utils.pytest_plugin import keywords

    def fake_locate(path, detect_threshold):
        return (10, 20)

    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_image.locate_image_center",
        fake_locate,
    )
    assert keywords.keyword_wait_for_image("x.png") == (10, 20)


def test_keyword_wait_for_image_times_out(monkeypatch):
    from je_auto_control.utils.exception.exceptions import (
        ImageNotFoundException,
    )
    from je_auto_control.utils.pytest_plugin import keywords

    def always_fail(path, detect_threshold):
        raise ImageNotFoundException("nope")

    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_image.locate_image_center",
        always_fail,
    )
    with pytest.raises(TimeoutError):
        keywords.keyword_wait_for_image("x.png", timeout=0.1)


# === BDD steps =============================================================

def test_bdd_then_screen_size_passes_when_matching(monkeypatch):
    from je_auto_control.utils.pytest_plugin import bdd_steps
    monkeypatch.setattr(bdd_steps, "keyword_screen_size",
                         lambda: (1920, 1080))
    bdd_steps.then_screen_size_equals(1920, 1080)


def test_bdd_then_screen_size_fails_with_assertion(monkeypatch):
    from je_auto_control.utils.pytest_plugin import bdd_steps
    monkeypatch.setattr(bdd_steps, "keyword_screen_size",
                         lambda: (640, 480))
    with pytest.raises(AssertionError):
        bdd_steps.then_screen_size_equals(1920, 1080)


def test_bdd_when_type_text_forwards_to_keyword(monkeypatch):
    from je_auto_control.utils.pytest_plugin import bdd_steps
    captured: list = []
    monkeypatch.setattr(bdd_steps, "keyword_type_text",
                         lambda text: captured.append(text))
    bdd_steps.when_type_text("hello world")
    assert captured == ["hello world"]


def test_bdd_when_click_image_forwards_to_keyword(monkeypatch):
    from je_auto_control.utils.pytest_plugin import bdd_steps
    monkeypatch.setattr(bdd_steps, "keyword_click_image",
                         lambda path: (1, 2))
    assert bdd_steps.when_click_image("x.png") == (1, 2)


def test_bdd_register_pytest_bdd_steps_wires_every_step():
    from je_auto_control.utils.pytest_plugin import bdd_steps

    mock_module = MagicMock()
    mock_module.parsers.parse = lambda template: template
    mock_module.given.return_value = lambda fn: fn
    mock_module.when.return_value = lambda fn: fn
    mock_module.then.return_value = lambda fn: fn

    bdd_steps.register_pytest_bdd_steps(mock_module)
    given_calls = [c.args[0] for c in mock_module.given.call_args_list]
    when_calls = [c.args[0] for c in mock_module.when.call_args_list]
    then_calls = [c.args[0] for c in mock_module.then.call_args_list]
    assert "AutoControl is ready" in given_calls
    assert any("I type" in tpl for tpl in when_calls)
    assert any("I see image" in tpl for tpl in then_calls)


def test_bdd_register_behave_steps_noop_without_behave():
    from je_auto_control.utils.pytest_plugin import bdd_steps
    # On systems without behave, the call must be a no-op (no exception).
    bdd_steps.register_behave_steps()


# === entry point ==========================================================

def test_pyproject_registers_pytest11_entry_point():
    import re
    from pathlib import Path
    raw = Path(__file__).resolve().parents[3].joinpath(
        "pyproject.toml",
    ).read_text(encoding="utf-8")
    assert re.search(r"\[project\.entry-points\.pytest11\]", raw)
    assert "je_auto_control.utils.pytest_plugin.plugin" in raw


# === plugin via pytester ==================================================

pytest_plugins = ["pytester"]


def test_plugin_capture_screenshot_on_failure(pytester, monkeypatch):
    """End-to-end: a failing test marked @autocontrol gets a screenshot."""
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.autocontrol
        def test_fails():
            assert False
        """,
    )
    # Patch the screenshot helper so we don't need a real display.
    pytester.makeconftest(
        """
        from unittest.mock import patch
        import pytest

        @pytest.fixture(autouse=True)
        def _patch_screenshot(tmp_path):
            with patch(
                "je_auto_control.wrapper.auto_control_screen.screenshot",
            ) as mocked:
                yield mocked
        """,
    )
    pytester.syspathinsert()
    result = pytester.runpytest("-p", "je_auto_control.utils.pytest_plugin.plugin")
    result.assert_outcomes(failed=1)


def test_plugin_no_screenshot_for_unmarked_failure(pytester):
    pytester.makepyfile(
        """
        def test_plain_failure():
            assert False
        """,
    )
    pytester.syspathinsert()
    result = pytester.runpytest("-p", "je_auto_control.utils.pytest_plugin.plugin")
    result.assert_outcomes(failed=1)
    out = result.stdout.str()
    assert "autocontrol-screenshot" not in out
