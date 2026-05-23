"""Join screen-frame manifest + action log into a scrubbable timeline."""
from __future__ import annotations

import bisect
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class ActionEvent:
    """One executor action that ran during the session."""
    timestamp: float
    action_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, body: Dict[str, Any]) -> "ActionEvent":
        return cls(
            timestamp=float(body.get("timestamp", 0.0)),
            action_name=str(body.get("action_name", "")),
            args=dict(body.get("args") or {}),
            result=body.get("result"),
            error=body.get("error"),
        )


@dataclass(frozen=True)
class FrameRef:
    """One frame in the JPEG manifest."""
    timestamp: float
    filename: str
    size: int = 0

    @classmethod
    def from_manifest_entry(cls, entry: Dict[str, Any]) -> "FrameRef":
        return cls(
            timestamp=float(entry.get("timestamp", 0.0)),
            filename=str(entry.get("filename", "")),
            size=int(entry.get("size", 0)),
        )


@dataclass
class TimelineSnapshot:
    """What :meth:`TimelinePlayer.at` returns — one point on the timeline."""
    step: int
    frame: Optional[FrameRef]
    actions: List[ActionEvent]
    relative_time_s: float


def load_action_log(path) -> List[ActionEvent]:
    """Load a ``actions.jsonl`` file (one JSON object per line)."""
    target = Path(os.path.expanduser(str(path)))
    events: List[ActionEvent] = []
    if not target.exists():
        return events
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(body, dict):
            events.append(ActionEvent.from_dict(body))
    return sorted(events, key=lambda e: e.timestamp)


def save_action_log(events: Sequence[ActionEvent], path) -> Path:
    """Write events as ``actions.jsonl`` — one JSON object per line."""
    target = Path(os.path.expanduser(str(path)))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            json.dumps(e.to_dict(), ensure_ascii=False)
            for e in events
        ) + ("\n" if events else ""),
        encoding="utf-8",
    )
    return target


class TimelinePlayer:
    """Wrap a JPEG manifest + action log into a scrubbable timeline.

    ``recording_dir`` should contain a ``manifest.json`` written by
    :class:`JpegSequenceRecorder` and an ``actions.jsonl`` written by
    :func:`save_action_log`. Either may be missing — the player just
    returns empty slices in that case.
    """

    def __init__(self, recording_dir) -> None:
        self._dir = Path(os.path.expanduser(str(recording_dir)))
        self._frames: List[FrameRef] = []
        self._actions: List[ActionEvent] = []
        self._timestamps: List[float] = []
        self._load()

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def action_count(self) -> int:
        return len(self._actions)

    @property
    def started_at(self) -> Optional[float]:
        if not self._frames and not self._actions:
            return None
        starts = []
        if self._frames:
            starts.append(self._frames[0].timestamp)
        if self._actions:
            starts.append(self._actions[0].timestamp)
        return min(starts)

    @property
    def stopped_at(self) -> Optional[float]:
        if not self._frames and not self._actions:
            return None
        ends = []
        if self._frames:
            ends.append(self._frames[-1].timestamp)
        if self._actions:
            ends.append(self._actions[-1].timestamp)
        return max(ends)

    @property
    def duration_s(self) -> float:
        start = self.started_at
        end = self.stopped_at
        if start is None or end is None:
            return 0.0
        return max(end - start, 0.0)

    def at_step(self, step: int) -> TimelineSnapshot:
        """Return the snapshot at the given frame ``step`` (0-indexed)."""
        if not self._frames:
            return TimelineSnapshot(step=0, frame=None, actions=[],
                                     relative_time_s=0.0)
        clamped = max(0, min(int(step), len(self._frames) - 1))
        return self._snapshot(clamped)

    def at_relative_time(self, seconds: float) -> TimelineSnapshot:
        """Return the snapshot at ``seconds`` past the session start."""
        if not self._frames:
            return TimelineSnapshot(step=0, frame=None, actions=[],
                                     relative_time_s=0.0)
        start = self.started_at or 0.0
        target = start + max(0.0, float(seconds))
        # bisect_right finds the insertion point just after target;
        # subtracting 1 gives the frame whose timestamp is ≤ target.
        idx = bisect.bisect_right(self._timestamps, target) - 1
        if idx < 0:
            idx = 0
        return self._snapshot(idx)

    def actions_in_window(self, start_ts: float,
                          end_ts: float) -> List[ActionEvent]:
        """Return every action whose timestamp falls inside ``[start, end]``."""
        if not self._actions:
            return []
        low = bisect.bisect_left(
            [a.timestamp for a in self._actions], float(start_ts),
        )
        high = bisect.bisect_right(
            [a.timestamp for a in self._actions], float(end_ts),
        )
        return list(self._actions[low:high])

    def load_frame_bytes(self, frame: FrameRef) -> bytes:
        """Read the raw JPEG payload for one frame."""
        target = self._dir / frame.filename
        return target.read_bytes()

    # --- internals ----------------------------------------------------

    def _load(self) -> None:
        manifest = self._dir / "manifest.json"
        if manifest.exists():
            body = json.loads(manifest.read_text(encoding="utf-8"))
            entries = body.get("entries") or []
            self._frames = [FrameRef.from_manifest_entry(e) for e in entries]
            self._frames.sort(key=lambda f: f.timestamp)
            self._timestamps = [f.timestamp for f in self._frames]
        actions_path = self._dir / "actions.jsonl"
        if actions_path.exists():
            self._actions = load_action_log(actions_path)

    def _snapshot(self, step: int) -> TimelineSnapshot:
        frame = self._frames[step]
        start = self.started_at or frame.timestamp
        if step + 1 < len(self._frames):
            window_end = self._frames[step + 1].timestamp
        elif self._actions:
            window_end = max(frame.timestamp, self._actions[-1].timestamp + 1e-3)
        else:
            window_end = frame.timestamp + 1.0
        actions = self.actions_in_window(frame.timestamp, window_end)
        return TimelineSnapshot(
            step=step, frame=frame,
            actions=actions,
            relative_time_s=round(frame.timestamp - start, 3),
        )


__all__ = [
    "ActionEvent", "FrameRef", "TimelinePlayer", "TimelineSnapshot",
    "load_action_log", "save_action_log",
]
