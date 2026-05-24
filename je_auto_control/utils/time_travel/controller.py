"""Stateful navigation wrapper around :class:`TimelinePlayer`.

The player itself is stateless — it answers "what's the snapshot at
step N?" but doesn't remember which step the user is currently on.
The Trace Replay GUI tab needs that state plus play/pause + step
forward/back semantics. Keeping it in a pure-Python controller lets
the headless tests cover every transition without spinning up Qt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from je_auto_control.utils.time_travel.player import (
    ActionEvent, FrameRef, TimelinePlayer, TimelineSnapshot,
)


@dataclass(frozen=True)
class ReplayState:
    """Snapshot-of-the-snapshot — what the UI should currently render."""

    step: int
    total_steps: int
    relative_time_s: float
    frame_filename: Optional[str]
    actions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TraceReplayController:
    """Cursor + navigation operations on top of :class:`TimelinePlayer`."""

    def __init__(self, player: TimelinePlayer) -> None:
        self._player = player
        self._step = 0

    @property
    def player(self) -> TimelinePlayer:
        return self._player

    @property
    def step(self) -> int:
        return self._step

    @property
    def total_steps(self) -> int:
        return self._player.frame_count

    def state(self) -> ReplayState:
        snapshot = self._player.at_step(self._step)
        return _render_state(snapshot, self.total_steps)

    def seek(self, step: int) -> ReplayState:
        self._step = _clamp(step, 0, max(0, self.total_steps - 1))
        return self.state()

    def step_forward(self) -> ReplayState:
        return self.seek(self._step + 1)

    def step_backward(self) -> ReplayState:
        return self.seek(self._step - 1)

    def jump_to_start(self) -> ReplayState:
        return self.seek(0)

    def jump_to_end(self) -> ReplayState:
        return self.seek(self.total_steps - 1)

    def seek_to_time(self, seconds: float) -> ReplayState:
        snapshot = self._player.at_relative_time(seconds)
        self._step = snapshot.step
        return _render_state(snapshot, self.total_steps)

    def jump_to_action(self, index: int) -> Optional[ReplayState]:
        """Seek to the frame whose window contains action ``index``."""
        actions = self._player_actions()
        if not actions or index < 0 or index >= len(actions):
            return None
        snapshot = self._player.at_relative_time(
            actions[index].timestamp - (self._player.started_at or 0.0),
        )
        self._step = snapshot.step
        return _render_state(snapshot, self.total_steps)

    def action_index(self) -> List[Dict[str, Any]]:
        """Flat list of every action with its absolute timestamp."""
        return [event.to_dict() for event in self._player_actions()]

    def _player_actions(self) -> List[ActionEvent]:
        # The player keeps actions internally; reuse the windowed view by
        # asking for the full range.
        if self.total_steps == 0:
            return list(self._player.actions_in_window(0.0, 0.0))
        start = self._player.started_at or 0.0
        end = self._player.stopped_at or start
        return list(self._player.actions_in_window(start, end + 1.0))


def _render_state(snapshot: TimelineSnapshot,
                   total_steps: int) -> ReplayState:
    return ReplayState(
        step=int(snapshot.step),
        total_steps=int(total_steps),
        relative_time_s=float(snapshot.relative_time_s),
        frame_filename=(
            snapshot.frame.filename if isinstance(snapshot.frame, FrameRef)
            else None
        ),
        actions=[event.to_dict() for event in snapshot.actions],
    )


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


__all__ = ["ReplayState", "TraceReplayController"]
