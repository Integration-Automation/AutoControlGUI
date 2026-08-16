"""Headless tests for the merged clipboard image API. No Qt.

``set_clipboard_image`` used to exist twice under the same name in this
package — ``clipboard.py`` took PNG bytes, ``clipboard_image.py`` took a path —
so importing the wrong module failed only at runtime, and only for whichever
argument type the caller happened to pass. There is one function now, and it
accepts both.
"""
import io
import sys

import pytest

from je_auto_control.utils.clipboard import clipboard as cb

pytest.importorskip("PIL", exc_type=ImportError)


def _png(size=(6, 4), colour=(10, 20, 30)) -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


# --- the conversion, tested without touching the real clipboard ------------

def test_bytes_pass_straight_through():
    payload = _png()
    assert cb._as_png_bytes(payload) == payload
    assert cb._as_png_bytes(bytearray(payload)) == payload


def test_a_path_is_read_and_re_encoded_as_png(tmp_path):
    from PIL import Image
    source = tmp_path / "shot.bmp"          # deliberately not a PNG
    Image.new("RGB", (9, 7), (1, 2, 3)).save(source)
    out = cb._as_png_bytes(str(source))
    assert out.startswith(b"\x89PNG\r\n\x1a\n")
    assert Image.open(io.BytesIO(out)).size == (9, 7)


def test_path_objects_work_too(tmp_path):
    from PIL import Image
    source = tmp_path / "shot.png"
    Image.new("RGB", (5, 5), (9, 9, 9)).save(source)
    assert cb._as_png_bytes(source).startswith(b"\x89PNG")


def test_empty_bytes_are_rejected():
    with pytest.raises(ValueError):
        cb._as_png_bytes(b"")


def test_a_missing_file_is_rejected_by_name(tmp_path):
    with pytest.raises(FileNotFoundError):
        cb._as_png_bytes(str(tmp_path / "absent.png"))


def test_a_directory_is_not_mistaken_for_an_image(tmp_path):
    """`realpath` + `isfile`, so a directory fails here rather than in Pillow."""
    with pytest.raises(FileNotFoundError):
        cb._as_png_bytes(str(tmp_path))


@pytest.mark.parametrize("bad", [123, None, 4.5, ["a"]])
def test_other_types_are_rejected(bad):
    with pytest.raises(TypeError):
        cb._as_png_bytes(bad)


# --- the real clipboard ----------------------------------------------------

@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="clipboard writes need the Windows backend here")
def test_round_trip_accepts_both_argument_forms(tmp_path):
    from PIL import Image
    source = tmp_path / "in.png"
    Image.new("RGB", (24, 16), (200, 40, 90)).save(source)

    cb.set_clipboard_image(str(source))          # the MCP / script form
    from_path = cb.get_clipboard_image()
    assert from_path and Image.open(io.BytesIO(from_path)).size == (24, 16)

    cb.set_clipboard_image(_png((8, 8)))         # the remote-desktop form
    from_bytes = cb.get_clipboard_image()
    assert from_bytes and Image.open(io.BytesIO(from_bytes)).size == (8, 8)


def test_the_duplicate_module_is_gone():
    """A stale import of the old module must fail loudly, not resurrect it."""
    with pytest.raises(ImportError):
        __import__("je_auto_control.utils.clipboard.clipboard_image")


def test_subpackage_exports_the_image_helpers():
    """They existed but were unreachable from the package or the facade."""
    import je_auto_control as ac
    from je_auto_control.utils import clipboard as pkg
    for name in ("get_clipboard_image", "set_clipboard_image"):
        assert name in pkg.__all__ and hasattr(pkg, name)
        assert name in ac.__all__ and hasattr(ac, name)
