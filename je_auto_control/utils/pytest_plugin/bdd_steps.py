"""Gherkin step definitions usable from pytest-bdd and behave.

Each step is a thin wrapper around one ``keyword_*`` helper in
:mod:`je_auto_control.utils.pytest_plugin.keywords`. The same function
works under both BDD frameworks because pytest-bdd and behave both
just import callables — they only differ on how those callables get
registered with the test runner.

Example (pytest-bdd, in ``conftest.py``)::

    from pytest_bdd import given, when, then, parsers
    from je_auto_control.utils.pytest_plugin import bdd_steps as ac_steps

    given("AutoControl is ready")(ac_steps.given_autocontrol_ready)
    when(parsers.parse("I type \"{text}\""))(ac_steps.when_type_text)
    then(parsers.parse("I see image \"{path}\""))(ac_steps.then_see_image)

Or use :func:`register_pytest_bdd_steps` to register every step in one call.
"""
from __future__ import annotations

from typing import Any, Optional

from je_auto_control.utils.pytest_plugin.keywords import (
    keyword_click_image, keyword_press_key, keyword_screen_size,
    keyword_screenshot, keyword_type_text, keyword_wait_for_image,
    keyword_wait_for_text,
)


# === Given =================================================================

def given_autocontrol_ready() -> None:
    """``Given AutoControl is ready`` — confirms the package imports."""
    import je_auto_control  # noqa: F401


# === When ==================================================================

def when_type_text(text: str) -> None:
    """``When I type "<text>"`` — types literal ``text``."""
    keyword_type_text(text)


def when_press_key(keycode: str) -> None:
    """``When I press "<keycode>"`` — presses one named key."""
    keyword_press_key(keycode)


def when_click_image(path: str) -> tuple:
    """``When I click on image "<path>"`` — locate + click."""
    return keyword_click_image(path)


def when_take_screenshot(path: str) -> str:
    """``When I take a screenshot to "<path>"`` — captures the screen."""
    return keyword_screenshot(path)


# === Then ==================================================================

def then_see_image(path: str, timeout: float = 10.0) -> tuple:
    """``Then I see image "<path>"`` — waits up to ``timeout`` seconds."""
    return keyword_wait_for_image(path, timeout=timeout)


def then_see_text(text: str, timeout: float = 10.0) -> tuple:
    """``Then I see text "<text>"`` — OCR wait."""
    return keyword_wait_for_text(text, timeout=timeout)


def then_screen_size_equals(width: int, height: int) -> None:
    """``Then the screen size is <width>x<height>`` — asserts dimensions."""
    actual_w, actual_h = keyword_screen_size()
    if (actual_w, actual_h) != (int(width), int(height)):
        raise AssertionError(
            f"expected screen size {width}x{height}, "
            f"got {actual_w}x{actual_h}",
        )


# === bulk registration helpers ============================================

def register_pytest_bdd_steps(pytest_bdd_module: Any) -> None:
    """Register every step against a pytest-bdd module in one call.

    Pass the module itself (``import pytest_bdd``) — we look up
    ``given``, ``when``, ``then``, ``parsers`` from it.
    """
    parsers = pytest_bdd_module.parsers
    given = pytest_bdd_module.given
    when = pytest_bdd_module.when
    then = pytest_bdd_module.then
    given("AutoControl is ready")(given_autocontrol_ready)
    when(parsers.parse('I type "{text}"'))(when_type_text)
    when(parsers.parse('I press "{keycode}"'))(when_press_key)
    when(parsers.parse('I click on image "{path}"'))(when_click_image)
    when(parsers.parse('I take a screenshot to "{path}"'))(when_take_screenshot)
    then(parsers.parse('I see image "{path}"'))(then_see_image)
    then(parsers.parse('I see text "{text}"'))(then_see_text)
    then(parsers.parse('the screen size is {width:d}x{height:d}'))(
        then_screen_size_equals,
    )


def register_behave_steps(context: Optional[Any] = None) -> None:
    """Register every step against the global ``behave`` registry.

    No-op when behave isn't installed. The optional ``context`` arg
    is reserved for future per-feature hooks and currently ignored.
    """
    try:
        from behave import given, when, then
    except ImportError:
        return
    given(u"AutoControl is ready")(given_autocontrol_ready)
    when(u'I type "{text}"')(when_type_text)
    when(u'I press "{keycode}"')(when_press_key)
    when(u'I click on image "{path}"')(when_click_image)
    when(u'I take a screenshot to "{path}"')(when_take_screenshot)
    then(u'I see image "{path}"')(then_see_image)
    then(u'I see text "{text}"')(then_see_text)
    then(u'the screen size is {width:d}x{height:d}')(then_screen_size_equals)


__all__ = [
    "given_autocontrol_ready", "register_behave_steps",
    "register_pytest_bdd_steps", "then_screen_size_equals",
    "then_see_image", "then_see_text", "when_click_image",
    "when_press_key", "when_take_screenshot", "when_type_text",
]
