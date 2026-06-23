"""Headless tests for 1-D barcode decoding. No Qt; decoder is injected."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.barcode import read_barcodes   # noqa: E402


def _image():
    return np.full((40, 120), 255, dtype=np.uint8)


def test_injected_decoder_is_used():
    rows = [{"text": "012345678905", "type": "EAN_13",
             "points": [[0, 0], [100, 0], [100, 30], [0, 30]]}]
    result = read_barcodes(_image(), decoder=lambda image: rows)
    assert result == rows


def test_decoder_receives_the_image():
    seen = {}

    def decoder(image):
        seen["shape"] = getattr(image, "shape", None)
        return []

    read_barcodes(_image(), decoder=decoder)
    assert seen["shape"] == (40, 120)


def test_default_decoder_blank_image_is_empty():
    # a blank image has no barcodes (graceful, regardless of cv2.barcode presence)
    assert read_barcodes(_image()) == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_read_barcodes" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_read_barcodes" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_read_barcodes" in specs


def test_facade_exports():
    assert hasattr(ac, "read_barcodes") and "read_barcodes" in ac.__all__
