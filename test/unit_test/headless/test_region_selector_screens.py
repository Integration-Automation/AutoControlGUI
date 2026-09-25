"""The region selector returns native pixels on every screen (offscreen Qt, two screens).

One overlay sized to the whole virtual desktop was put on the primary screen by
showFullScreen, yet its result was still offset by the virtual desktop's origin:
with a second screen 164 px higher, every region came out 164 px too high. A
screen at 125% was not covered, and would have answered in logical pixels.
"""
import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from headless._exit_probe import run_probe  # noqa: E402

_PROBE = r'''
import json, os, sys, tempfile
from pathlib import Path
work = Path(tempfile.mkdtemp())
(work / "screens.json").write_text(json.dumps({"screens": [
    {"name": "primary", "x": 0, "y": 0, "width": 1920, "height": 1080},
    {"name": "scaled", "x": 1920, "y": -164, "width": 1536, "height": 864, "dpr": 1.25}]}),
    encoding="utf-8")
os.chdir(work)   # platform options are colon-separated: no drive letter in the path
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=screens.json"
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
app = QApplication([])
from je_auto_control.gui.selector.region_overlay import RegionOverlay, pick_region_blocking
if sys.argv[1].endswith("-mac"):
    sys.platform = "darwin"      # captures and the pointer take points there

def drag():
    overlays = [w for w in QApplication.topLevelWidgets() if isinstance(w, RegionOverlay) and w.isVisible()]
    if sys.argv[1] == "close":
        overlays[0].close()              # closed without a selection
        return
    for overlay in overlays:
        if overlay.screen().name() == sys.argv[1].split("-")[0]:
            QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
            QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(300, 200))
            return
    for overlay in overlays:
        overlay.close()

QTimer.singleShot(0, drag)
print("region", pick_region_blocking(), flush=True)
'''


@pytest.mark.parametrize("screen, region", [
    ("primary", "(100, 100, 201, 101)"),
    # (1920 + 100 * 1.25, -164 + 100 * 1.25, 201 * 1.25, 101 * 1.25), rounded
    ("scaled", "(2045, -39, 251, 126)"),
    # macOS: Qt's logical pixels are the points captures take, so no scaling
    ("scaled-mac", "(2020, -64, 201, 101)"),
])
def test_a_drag_answers_in_native_pixels_on_its_screen(screen, region):
    done = run_probe(_PROBE, screen)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == f"region {region}"


def test_an_overlay_closed_without_a_selection_is_a_cancel():
    done = run_probe(_PROBE, "close")
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "region None"
