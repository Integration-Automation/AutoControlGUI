"""Assertion DSL — screen-state verification for automation scripts.

Public surface::

    from je_auto_control import (
        assert_text, assert_image, assert_pixel, assert_window,
        assert_clipboard, assert_all, assert_eventually,
        AssertionResult, GroupAssertionResult,
    )
"""
from je_auto_control.utils.assertion.assertions import (
    AssertionResult,
    assert_by_description,
    assert_clipboard,
    assert_duration,
    assert_file,
    assert_http,
    assert_image,
    assert_pixel,
    assert_process,
    assert_text,
    assert_window,
)
from je_auto_control.utils.assertion.combinators import (
    GroupAssertionResult,
    assert_all,
    assert_any,
    assert_eventually,
    run_assertion_spec,
)


__all__ = [
    "AssertionResult",
    "GroupAssertionResult",
    "assert_all",
    "assert_any",
    "assert_by_description",
    "assert_clipboard",
    "assert_duration",
    "assert_eventually",
    "assert_file",
    "assert_http",
    "assert_image",
    "assert_pixel",
    "assert_process",
    "assert_text",
    "assert_window",
    "run_assertion_spec",
]
