"""Assertion DSL — screen-state verification for automation scripts.

Public surface::

    from je_auto_control import (
        assert_text, assert_image, assert_pixel, assert_window,
        AssertionResult,
    )
"""
from je_auto_control.utils.assertion.assertions import (
    AssertionResult,
    assert_image,
    assert_pixel,
    assert_text,
    assert_window,
)


__all__ = [
    "AssertionResult",
    "assert_image",
    "assert_pixel",
    "assert_text",
    "assert_window",
]
