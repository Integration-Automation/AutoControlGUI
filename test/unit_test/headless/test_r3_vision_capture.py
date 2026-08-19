"""R3 regression: recorder stop, frame-diff pixel counting, screenshot save.

Covers:
* ScreenRecordThread ignoring a stop() that lands before run() (run() set the
  flag True unconditionally), leaving it unstoppable and the writer un-released.
* smart_waits._frame_diff counting differing BYTES instead of PIXELS, so a
  one-pixel blink read as three and wait_until_screen_stable(max_pixel_diff=2)
  never settled.
* pil_screenshot swallowing a save failure and returning the image anyway, so a
  requested screenshot file could silently not exist.
"""
import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.cv2_utils import screen_record as sr    # noqa: E402
from je_auto_control.utils.cv2_utils import screenshot as ss       # noqa: E402
from je_auto_control.utils.smart_waits import waits                # noqa: E402
from je_auto_control.utils.exception.exceptions import (           # noqa: E402
    AutoControlScreenException,
)


class _FakeVideoWriter:
    """Stand-in for cv2.VideoWriter that never touches a real file."""

    @staticmethod
    def fourcc(*_codec):
        return 0

    def __init__(self, *_args, **_kwargs):
        self.writes = 0
        self.released = False

    def write(self, _frame):
        self.writes += 1

    def release(self):
        self.released = True


# --- finding 2: recorder stop honoured + writer released -----------------

def test_stop_before_run_is_honored(monkeypatch):
    monkeypatch.setattr(sr.cv2, "VideoWriter", _FakeVideoWriter)
    thread = sr.ScreenRecordThread("out.avi", "XVID", 30, (4, 4))
    frame = np.zeros((4, 4, 3), dtype=np.uint8)

    def screenshot_bounds_the_buggy_path():
        # If the pre-run stop() is overwritten (old bug), stopping here bounds
        # the loop to a single frame so the test cannot hang; the assertions
        # below still detect that the loop body ran.
        thread.stop()
        return frame

    monkeypatch.setattr(sr, "screenshot", screenshot_bounds_the_buggy_path)

    thread.stop()      # stop BEFORE the thread body runs
    thread.run()       # run synchronously

    assert thread.video_writer.writes == 0        # loop body never executed
    assert thread.video_writer.released is True   # writer always released


def test_normal_run_writes_frames_and_releases(monkeypatch):
    monkeypatch.setattr(sr.cv2, "VideoWriter", _FakeVideoWriter)
    thread = sr.ScreenRecordThread("out.avi", "XVID", 30, (4, 4))
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    calls = {"n": 0}

    def screenshot_stop_after_two():
        calls["n"] += 1
        if calls["n"] >= 2:
            thread.stop()
        return frame

    monkeypatch.setattr(sr, "screenshot", screenshot_stop_after_two)
    thread.run()

    assert thread.video_writer.writes == 2
    assert thread.video_writer.released is True


# --- finding 4: frame diff counts pixels, not bytes ----------------------

def test_frame_diff_counts_pixels_not_bytes():
    base = bytes([0, 0, 0] * 4)               # 2x2 RGB, all black
    changed = bytearray(base)
    changed[0:3] = bytes([255, 255, 255])     # one pixel, three differing bytes
    a = waits.Frame(2, 2, base)
    b = waits.Frame(2, 2, bytes(changed))
    assert waits._frame_diff(a, b) == 1       # one pixel, not three bytes


def test_screen_stable_settles_on_one_pixel_blink():
    base = bytes([10, 20, 30] * 4)
    blink = bytearray(base)
    blink[0:3] = bytes([200, 200, 200])       # a one-pixel change
    frames = [base, bytes(blink)]
    state = {"i": 0}

    def sampler(_region):
        # Alternate base <-> blink forever: consecutive frames always differ by
        # exactly one pixel, so a pixel-aware diff (<=2) settles immediately
        # while the old byte-aware diff (=3) never would.
        frame = frames[state["i"] % 2]
        state["i"] += 1
        return waits.Frame(2, 2, frame)

    outcome = waits.wait_until_screen_stable(
        timeout_s=0.2, poll_interval_s=0.001, stable_for_s=0.0,
        max_pixel_diff=2, sampler=sampler,
    )
    assert outcome.succeeded is True


# --- finding 7: screenshot save failure raises ---------------------------

class _FakeGrab:
    @staticmethod
    def grab(*_args, **_kwargs):
        from PIL import Image
        return Image.new("RGB", (4, 4))


def test_screenshot_save_failure_raises(monkeypatch, tmp_path):
    pytest.importorskip("PIL")
    # pil_screenshot now asks the platform layer for its grabber rather than
    # importing ImageGrab itself, so Wayland gets the compositor's capture.
    monkeypatch.setattr(ss, "image_grabber", lambda: _FakeGrab)
    bad_path = str(tmp_path / "no_such_dir" / "shot.png")   # parent missing
    with pytest.raises(AutoControlScreenException):
        ss.pil_screenshot(file_path=bad_path)
