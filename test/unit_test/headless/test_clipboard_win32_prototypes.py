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

That real clipboard is machine-global, which used to make these tests depend on
what every *other* process on the box was doing: one write from anything else
between our write and our read failed the run, and during a parallel Docker
build one did. :func:`_round_trip` closes that hole without giving up the real
Win32 calls — see its docstring for why faking the backend instead would delete
the only coverage this file has.
"""
import sys

import pytest

_WINDOWS = sys.platform.startswith("win")
pytestmark = pytest.mark.skipif(not _WINDOWS, reason="Windows clipboard only")

# How many times a stolen round-trip is worth re-running before giving up.
_ATTEMPTS = 4


def _clipboard_available() -> bool:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard
    try:
        get_clipboard()
        return True
    except Exception:  # noqa: BLE001 - locked desktop / no window station
        return False


def _sequence_number() -> int:
    """Win32's clipboard change counter for this window station.

    It moves on every *modification*, by any process, and never on a read —
    which is precisely the signal needed to tell "somebody stole my clipboard"
    from "my writer is broken".
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClipboardSequenceNumber.argtypes = []
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    return int(user32.GetClipboardSequenceNumber())


def _round_trip(write, read):
    """Run ``write`` then ``read`` as one uninterrupted pair; return the value.

    Faking the clipboard backend would make this file deterministic by
    deleting the only thing it tests — the Win32 half, which is where all four
    historical bugs were and which no pure-function test could reach. So the
    calls stay real and the *interference* is detected instead: if the
    sequence number has not moved between the end of our write and the end of
    our read, nothing else wrote in that window, so the bytes we read are the
    bytes we wrote and the assertion that follows is about our code alone.

    Nothing that looks like a bug is retried away: ``write`` raising is the
    exact shape of the regression this file exists to catch, so it propagates
    on the first attempt. The other half of the race — a clipboard another
    process is holding *open* — is not handled here at all, because
    ``win32_clipboard_api.open_clipboard`` waits that out for every caller of
    the library, not just for this test.
    """
    for _attempt in range(_ATTEMPTS):
        write()
        stamp = _sequence_number()
        value = read()
        if _sequence_number() == stamp:
            return value
    pytest.skip("another process kept overwriting the clipboard")
    return None  # unreachable; keeps the return type honest for linters


@pytest.fixture
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
    read_back = _round_trip(lambda: set_clipboard("round-trip probe"),
                            get_clipboard)
    assert read_back == "round-trip probe"


def test_html_round_trip(clipboard):
    from je_auto_control.utils.rich_clipboard.rich_clipboard import (
        get_clipboard_html, set_clipboard_html,
    )
    read_back = _round_trip(lambda: set_clipboard_html("<b>hi</b>"),
                            get_clipboard_html)
    assert "hi" in (read_back or "")


def test_rtf_round_trip(clipboard):
    from je_auto_control.utils.clipboard_rich_formats.clipboard_rich_formats import (
        build_rtf, get_clipboard_rtf, set_clipboard_rtf,
    )
    read_back = _round_trip(lambda: set_clipboard_rtf(build_rtf("hello")),
                            get_clipboard_rtf)
    assert "hello" in (read_back or "")


def test_csv_round_trip(clipboard):
    from je_auto_control.utils.clipboard_rich_formats.clipboard_rich_formats import (
        get_clipboard_csv, set_clipboard_csv,
    )
    read_back = _round_trip(
        lambda: set_clipboard_csv([["a", "b"], ["c", "d"]]),
        get_clipboard_csv,
    )
    assert read_back == [["a", "b"], ["c", "d"]]


def test_file_list_round_trip(clipboard, tmp_path):
    from je_auto_control.utils.clipboard_files.clipboard_files import (
        get_clipboard_files, set_clipboard_files,
    )
    one = tmp_path / "one.png"
    one.write_bytes(b"x")
    read_back = _round_trip(lambda: set_clipboard_files([str(one)]),
                            get_clipboard_files)
    assert read_back == [str(one)]


def test_format_enumeration_sees_what_was_written(clipboard):
    from je_auto_control.utils.clipboard.clipboard import set_clipboard
    from je_auto_control.utils.clipboard_formats.clipboard_formats import (
        clipboard_formats,
    )
    summary = _round_trip(lambda: set_clipboard("text only"), clipboard_formats)
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
