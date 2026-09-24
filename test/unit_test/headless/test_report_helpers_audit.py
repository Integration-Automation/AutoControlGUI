"""Report-helper defects from the 2026-09-24 audit.

A generator of steps gave an empty walkthrough video without an error; a
rubric string was checked letter by letter; and a failure bundle recorded
``str(error)`` only, which is empty for ``TimeoutError()``.
"""
import json
import zipfile

from je_auto_control.utils.failure_bundle.bundle import (
    FailureBundleOptions, create_failure_bundle,
)
from je_auto_control.utils.trajectory_eval.trajectory_eval import evaluate_trajectory
from je_auto_control.utils.video_report.video_report import write_step_video


class _Frame:
    shape = (4, 6, 3)


class _Writer:
    def __init__(self):
        self.frames = 0

    def isOpened(self):  # noqa: N802 - OpenCV name
        return True

    def write(self, _frame):
        self.frames += 1

    def release(self):
        pass


def test_a_generator_of_steps_renders_every_frame(tmp_path):
    steps = ({"image": "shot.png", "caption": f"step {n}", "status": "ok"} for n in range(2))
    result = write_step_video(
        steps, str(tmp_path / "walk.mp4"), fps=5, seconds_per_step=1.0,
        loader=lambda _image: _Frame(), drawer=lambda frame, *_a, **_k: frame,
        writer_factory=lambda *_a, **_k: _Writer())
    assert result["steps"] == 2
    assert result["frame_count"] == 10


def test_a_rubric_string_names_one_action():
    trajectory = [{"action": "A"}, {"action": "C"}]
    assert not evaluate_trajectory(trajectory, {"required_actions": "AC"})["passed"]
    assert not evaluate_trajectory([{"action": "click"}], {"forbidden_actions": "click"})["passed"]
    assert evaluate_trajectory(trajectory, {"required_actions": ["A", "C"]})["passed"]


def test_the_bundle_names_the_error_type(tmp_path):
    path = create_failure_bundle(
        str(tmp_path / "b.zip"), error=TimeoutError(),
        options=FailureBundleOptions(screenshot=False, diagnostics=False))
    with zipfile.ZipFile(path) as bundle:
        name = next(entry for entry in bundle.namelist() if entry.endswith("manifest.json"))
        manifest = json.loads(bundle.read(name))
    assert manifest["error_type"] == "TimeoutError"
