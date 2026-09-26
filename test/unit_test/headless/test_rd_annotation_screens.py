"""Host annotations land where the viewer drew them, on any screen and scale.

The viewer draws in frame pixels. The overlay drew them as its own logical
pixels on the primary screen: off by the frame's origin (another monitor, a
region), and on a scaled screen by its device pixel ratio.
"""
import types

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
from PySide6.QtWidgets import QApplication
app = QApplication([])
from je_auto_control.gui.remote_desktop.annotation_overlay import HostAnnotationOverlay
# Pinned both ways, as the plain cases read darwin on a macOS runner.
sys.platform = "darwin" if sys.argv[1].endswith("-mac") else "linux"
overlay = HostAnnotationOverlay()
origin = [1920, -164] if sys.argv[1].startswith("scaled") else [0, 0]
overlay.apply({"action": "begin", "x": 10, "y": 20, "screen_origin": origin})
print(overlay._target.name(), overlay._strokes[-1]["points"][0], flush=True)
'''


@pytest.mark.parametrize("screen, expected", [
    ("primary", "primary (10.0, 20.0)"),
    # native (1930, -144) on the 125% screen: 1920 + 10 / 1.25, -164 + 20 / 1.25, less its corner
    ("scaled", "scaled (8.0, 16.0)"),
    # macOS: captures and Qt both take points, so the frame pixel is the logical pixel
    ("scaled-mac", "scaled (10.0, 20.0)"),
])
def test_a_point_is_drawn_on_its_screen_in_its_pixels(screen, expected):
    done = run_probe(_PROBE, screen)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == expected


def test_the_hosts_stamp_the_frame_origin_over_the_viewers():
    pytest.importorskip("aiortc")
    pytest.importorskip("av")
    from je_auto_control.utils.remote_desktop.multi_viewer import MultiViewerHost
    from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost
    from je_auto_control.utils.remote_desktop.webrtc_transport import ScreenVideoTrack
    seen = []
    single = WebRTCDesktopHost(token="t", on_annotation=seen.append)
    single._video_track = ScreenVideoTrack(region=[1920, -164, 1920, 1080])
    single._handle_annotate({"type": "annotate", "action": "begin", "x": 1, "y": 2, "screen_origin": [5, 5]})
    multi = MultiViewerHost(token="t", on_annotation=seen.append)
    multi._source = types.SimpleNamespace(capture_origin=(100, 200))
    multi._annotate({"action": "point", "x": 1, "y": 2, "screen_origin": [5, 5]})
    assert [event["screen_origin"] for event in seen] == [(1920, -164), (100, 200)]
    single._video_track.stop()
