"""The Win32 message module has to be importable, and must not edit ctypes.

Both of these were found by the typing contract rather than by anything that
ran: ``window_message`` imported a name its source module does not export, so
the module raised ``ImportError`` on every Windows machine and nothing in the
shipping path noticed because only a manual test imports it. And
``win32_ctype_input`` wrote ``ULONG_PTR`` into the standard library's own
``ctypes.wintypes`` namespace, which no code in this package ever read back —
so the only thing that assignment could do was answer for someone else's
``hasattr(wintypes, "ULONG_PTR")``.
"""
import ctypes
import sys
from ctypes import wintypes

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform not in ("win32", "cygwin", "msys"),
    reason="Windows input backend modules only import on Windows.",
)


def test_window_message_module_imports():
    """It used to raise ImportError before any of its functions were reachable."""
    from je_auto_control.windows.message import window_message

    for name in ("send_message_to_window", "send_message_to_window_hwnd",
                 "post_message_to_window", "post_message_to_window_hwnd"):
        assert callable(getattr(window_message, name))
    assert window_message.messages["WM_CLOSE"] == 0x0010


def test_window_lookup_goes_through_the_prototyped_helper():
    """The helper it calls is the one that declares HWND-width argtypes.

    ``FindWindowW`` off a raw handle defaults to ``c_int``, which truncates a
    64-bit HWND; ``get_one_window_hwnd`` sets the prototype first.
    """
    from je_auto_control.windows.message import window_message
    from je_auto_control.windows.window import windows_window_manage

    assert window_message.get_one_window_hwnd is (
        windows_window_manage.get_one_window_hwnd)
    missing = "je_auto_control window that does not exist 0f3a"
    assert windows_window_manage.get_one_window_hwnd(None, missing) == 0


def test_importing_the_input_module_leaves_ctypes_alone():
    """Importing a backend must not add names to a standard library module."""
    import je_auto_control.windows.core.utils.win32_ctype_input  # noqa: F401  # reason: imported for its side effects, which is what this asserts about

    assert not hasattr(wintypes, "ULONG_PTR")
    assert not hasattr(ctypes.wintypes, "ULONG_PTR")
