"""Round-trip tests for the headless clipboard."""
import shutil
import sys

import pytest

from je_auto_control.utils.clipboard.clipboard import get_clipboard, set_clipboard


def _clipboard_available() -> bool:
    if sys.platform.startswith("win"):
        return True
    if sys.platform == "darwin":
        return shutil.which("pbcopy") is not None
    return shutil.which("xclip") is not None or shutil.which("xsel") is not None


pytestmark = pytest.mark.skipif(
    not _clipboard_available(),
    reason="no clipboard backend available on this host",
)


def test_set_and_get_roundtrip():
    payload = "AutoControl clipboard 測試 🎯"
    set_clipboard(payload)
    assert get_clipboard() == payload


def test_set_clipboard_rejects_non_string():
    with pytest.raises(TypeError):
        set_clipboard(123)  # type: ignore[arg-type]  # NOSONAR
