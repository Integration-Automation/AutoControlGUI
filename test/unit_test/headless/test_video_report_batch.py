"""Headless tests for the video step-overlay report. The assembly logic is
exercised with injected fakes (no cv2/numpy needed); one test exercises the
real OpenCV path under importorskip. Pure stdlib otherwise; no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.video_report import (
    VideoStep, build_overlay_plan, render_overlay_frame, write_step_video)

STEPS = [
    {"image": "a.png", "caption": "Open app", "status": "ok"},
    {"image": "b.png", "caption": "Save", "status": "error"},
]


class _FakeWriter:
    def __init__(self):
        self.frames = []
        self.released = False

    def write(self, frame):
        self.frames.append(frame)

    def release(self):
        self.released = True


def test_plan_frame_count():
    plan = build_overlay_plan(STEPS, fps=10, seconds_per_step=2.0)
    assert [p["frames"] for p in plan] == [20, 20]
    assert plan[0]["caption"] == "Open app"
    assert plan[1]["status"] == "error"


def test_plan_minimum_one_frame():
    plan = build_overlay_plan([VideoStep("x")], fps=1, seconds_per_step=0.0)
    assert plan[0]["frames"] == 1


def test_render_overlay_uses_injected_drawer():
    seen = {}

    def drawer(frame, caption, status):
        seen["args"] = (frame, caption, status)
        return f"{frame}+{caption}"

    out = render_overlay_frame("FRAME", "hi", "ok", drawer=drawer)
    assert out == "FRAME+hi"
    assert seen["args"] == ("FRAME", "hi", "ok")


def test_write_step_video_with_fakes(tmp_path):
    writer = _FakeWriter()
    loaded = []

    def loader(image):
        loaded.append(image)
        return f"frame:{image}"

    def drawer(frame, caption, status):
        return f"{frame}|{caption}|{status}"

    result = write_step_video(
        STEPS, str(tmp_path / "out.mp4"), fps=5, seconds_per_step=2.0,
        size=(640, 480), loader=loader, drawer=drawer,
        writer_factory=lambda path, fps, size: writer)

    assert loaded == ["a.png", "b.png"]
    assert result["steps"] == 2
    assert result["frame_count"] == 20            # 2 steps * (5fps * 2s)
    assert len(writer.frames) == 20
    assert writer.frames[0] == "frame:a.png|Open app|ok"
    assert writer.released is True                 # released in finally


def test_writer_released_on_error(tmp_path):
    writer = _FakeWriter()

    def exploding_write(_frame):
        raise RuntimeError("disk full")

    writer.write = exploding_write
    with pytest.raises(RuntimeError):
        write_step_video(
            [VideoStep("a.png", "x")], str(tmp_path / "o.mp4"),
            size=(8, 8), loader=lambda i: "f", drawer=lambda f, c, s: f,
            writer_factory=lambda p, fp, sz: writer)
    assert writer.released is True


def test_real_opencv_path(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    drawn = render_overlay_frame(frame.copy(), "hello", "ok")
    assert drawn.shape == frame.shape         # banner drawn in place

    out = str(tmp_path / "real.mp4")
    result = write_step_video([VideoStep(frame, "step", "ok")], out,
                              fps=5, seconds_per_step=0.4)
    assert result["frame_count"] == 2
    assert cv2 is not None


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_write_step_video" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_write_step_video" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_write_step_video" in cmds


def test_facade_exports():
    for attr in ("VideoStep", "build_overlay_plan", "render_overlay_frame",
                 "write_step_video"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
