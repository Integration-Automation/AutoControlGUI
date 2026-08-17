"""Every clipboard format must survive a real round-trip, and no module may
hand-roll the Win32 calls again. No Qt.

Three ``set_clipboard_*`` functions were broken on 64-bit Windows for their
whole existence — HTML, RTF and CSV — and so was the file-drop writer. All four
failed the same way: the module declared ``restype`` but not ``argtypes``, so
ctypes passed a pointer-width memory handle as ``c_int`` and ``GlobalLock``
raised ``OverflowError: int too long to convert``. Pure-function tests could not
see it (the byte packing was always correct) and no test called the Win32 half.

So this file tests the half that was untested: the actual clipboard. It skips
when the clipboard cannot be opened at all — a locked workstation, a session
without a window station, or a non-Windows CI runner — rather than reporting a
failure the environment made inevitable.
"""
import sys

import pytest

_WINDOWS = sys.platform.startswith("win")
pytestmark = pytest.mark.skipif(not _WINDOWS, reason="Windows clipboard only")


def _clipboard_available() -> bool:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard
    try:
        get_clipboard()
        return True
    except Exception:  # noqa: BLE001 - locked desktop / no window station
        return False


@pytest.fixture()
def clipboard():
    """Skip when unusable, and put the user's clipboard back afterwards."""
    if not _clipboard_available():
        pytest.skip("clipboard cannot be opened in this session")
    from je_auto_control.utils.clipboard.clipboard import (
        get_clipboard, set_clipboard,
    )
    saved = get_clipboard()
    try:
        yield
    finally:
        try:
            set_clipboard(saved)
        except Exception:  # noqa: BLE001  # nosec B110
            pass


def test_text_round_trip(clipboard):
    from je_auto_control.utils.clipboard.clipboard import (
        get_clipboard, set_clipboard,
    )
    set_clipboard("round-trip probe")
    assert get_clipboard() == "round-trip probe"


def test_html_round_trip(clipboard):
    from je_auto_control.utils.rich_clipboard.rich_clipboard import (
        get_clipboard_html, set_clipboard_html,
    )
    set_clipboard_html("<b>hi</b>")
    assert "hi" in (get_clipboard_html() or "")


def test_rtf_round_trip(clipboard):
    from je_auto_control.utils.clipboard_rich_formats.clipboard_rich_formats import (
        build_rtf, get_clipboard_rtf, set_clipboard_rtf,
    )
    set_clipboard_rtf(build_rtf("hello"))
    assert "hello" in (get_clipboard_rtf() or "")


def test_csv_round_trip(clipboard):
    from je_auto_control.utils.clipboard_rich_formats.clipboard_rich_formats import (
        get_clipboard_csv, set_clipboard_csv,
    )
    set_clipboard_csv([["a", "b"], ["c", "d"]])
    assert get_clipboard_csv() == [["a", "b"], ["c", "d"]]


def test_file_list_round_trip(clipboard, tmp_path):
    from je_auto_control.utils.clipboard_files.clipboard_files import (
        get_clipboard_files, set_clipboard_files,
    )
    one = tmp_path / "one.png"
    one.write_bytes(b"x")
    set_clipboard_files([str(one)])
    assert get_clipboard_files() == [str(one)]


def test_format_enumeration_sees_what_was_written(clipboard):
    from je_auto_control.utils.clipboard.clipboard import set_clipboard
    from je_auto_control.utils.clipboard_formats.clipboard_formats import (
        clipboard_formats,
    )
    set_clipboard("text only")
    summary = clipboard_formats()
    assert summary["has_text"] is True
    assert summary["has_files"] is False


# --- static invariant -------------------------------------------------------

_HANDLE_CALLS = ("GlobalLock", "GlobalAlloc", "GlobalSize", "SetClipboardData",
                 "GetClipboardData")
_SHARED_MODULE = "win32_clipboard_api"


def test_no_module_hand_rolls_the_clipboard_calls_without_prototypes():
    """A handle call needs declared ``argtypes`` — in the file or via the shared module.

    This is the invariant the three broken modules violated. Any new clipboard
    code either goes through ``utils/clipboard/win32_clipboard_api.py`` or
    declares the prototypes itself; ``restype``-only is what shipped a function
    that had never once worked.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3] / "je_auto_control"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not any(call in text for call in _HANDLE_CALLS):
            continue
        if _SHARED_MODULE in text or "argtypes" in text:
            continue
        offenders.append(str(path.relative_to(root)))
    assert not offenders, (
        "these modules call Win32 handle APIs without declaring argtypes and "
        "without going through the shared clipboard module: " + repr(offenders)
    )
