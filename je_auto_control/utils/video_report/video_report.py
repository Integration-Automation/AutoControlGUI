"""Assemble captioned screenshots into a step-by-step walkthrough video.

A run already produces per-step screenshots; this turns them into an MP4/AVI
where each step's frame is held for a few seconds with its caption (and a
pass/fail colour banner) burned in — a shareable visual report of what the
automation did. The orchestration (which frames, how many repeats per step,
which caption) is separated from OpenCV: ``loader`` / ``drawer`` /
``writer_factory`` are injectable, so the assembly logic is unit-testable with
fakes and **no** ``cv2``/``numpy`` dependency. The real path lazily imports
``cv2`` only when those hooks are not supplied.

Imports no ``PySide6``.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

STATUS_COLORS = {
    "ok": (40, 160, 40), "error": (40, 40, 200), "": (60, 60, 60),
}


@dataclass
class VideoStep:
    """One step: an image (path or frame) plus a caption and optional status."""

    image: Any
    caption: str = ""
    status: str = ""


def _coerce_step(step: Any) -> VideoStep:
    if isinstance(step, VideoStep):
        return step
    if isinstance(step, dict):
        return VideoStep(step.get("image"), step.get("caption", ""),
                         str(step.get("status", "")))
    raise TypeError(f"unsupported step type: {type(step).__name__}")


def build_overlay_plan(steps: Sequence[Any], fps: int = 10,
                       seconds_per_step: float = 2.0) -> List[Dict[str, Any]]:
    """Return per-step ``{caption, status, frames}`` (no I/O, no cv2).

    ``frames`` is how many times the step's frame is written
    (``round(fps * seconds_per_step)``, at least 1).
    """
    frames = max(1, round(fps * seconds_per_step))
    plan: List[Dict[str, Any]] = []
    for step in steps:
        coerced = _coerce_step(step)
        plan.append({"caption": coerced.caption, "status": coerced.status,
                     "frames": frames})
    return plan


def _default_drawer(frame: Any, caption: str, status: str) -> Any:
    import cv2
    height, width = frame.shape[0], frame.shape[1]
    color = STATUS_COLORS.get(status, STATUS_COLORS[""])
    banner_top = max(0, height - 60)
    cv2.rectangle(frame, (0, banner_top), (width, height), color, thickness=-1)
    cv2.putText(frame, caption, (15, height - 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def render_overlay_frame(frame: Any, caption: str, status: str = "",
                         drawer: Optional[Callable[..., Any]] = None) -> Any:
    """Burn ``caption`` and a status banner onto ``frame`` and return it."""
    return (drawer or _default_drawer)(frame, caption, status)


def _default_loader(image: Any) -> Any:
    if isinstance(image, str):
        import cv2
        frame = cv2.imread(image)
        if frame is None:
            raise FileNotFoundError(f"could not read image: {image!r}")
        return frame
    return image


def _default_writer_factory(path: str, fps: int, size: Any) -> Any:
    import cv2
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    return cv2.VideoWriter(path, fourcc, fps, size)


def _frame_size(frame: Any) -> Any:
    return (frame.shape[1], frame.shape[0])


def write_step_video(steps: Sequence[Any], output_path: str, *,
                     fps: int = 10, seconds_per_step: float = 2.0,
                     size: Optional[Any] = None,
                     loader: Optional[Callable[[Any], Any]] = None,
                     drawer: Optional[Callable[..., Any]] = None,
                     writer_factory: Optional[Callable[..., Any]] = None
                     ) -> Dict[str, Any]:
    """Render ``steps`` into a captioned walkthrough video at ``output_path``.

    Returns ``{output, steps, fps, frame_count}``. The ``loader`` /
    ``drawer`` / ``writer_factory`` hooks default to OpenCV; injecting them
    makes the assembly testable without cv2.
    """
    load = loader or _default_loader
    plan = build_overlay_plan(steps, fps, seconds_per_step)
    coerced = [_coerce_step(step) for step in steps]
    rendered = [render_overlay_frame(load(step.image), entry["caption"],
                                     entry["status"], drawer)
                for step, entry in zip(coerced, plan)]
    if size is None and rendered:
        size = _frame_size(rendered[0])
    writer = (writer_factory or _default_writer_factory)(output_path, fps, size)
    frame_count = 0
    try:
        for frame, entry in zip(rendered, plan):
            for _ in range(entry["frames"]):
                writer.write(frame)
                frame_count += 1
    finally:
        writer.release()
    return {"output": output_path, "steps": len(plan), "fps": fps,
            "frame_count": frame_count}
