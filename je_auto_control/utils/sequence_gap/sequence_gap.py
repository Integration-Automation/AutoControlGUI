"""Per-stream sequence-gap / ordering detection.

Nothing tracked per-stream monotonic sequence numbers to detect missing,
out-of-order, or duplicate messages. ``dedup_window`` says "seen this id
before"; this complements it by classifying each sequence number as ``ok`` /
``duplicate`` / ``gap`` (numbers skipped ahead) / ``reorder`` (a late arrival),
and tracking the outstanding gaps and high-water mark per stream.

Pure standard library; imports no ``PySide6``. State is in-memory and fully
injectable, so detection is deterministic in CI.
"""
from typing import Any, Dict, List


class SequenceTracker:
    """Tracks per-stream sequence numbers and classifies each observation.

    Every number from the first one observed up to the high-water mark is
    either seen or an outstanding gap, so only the gaps (and any late numbers
    below the first) are stored; keeping every seen number grew without
    bound. The outstanding gaps are capped at ``max_gap``: a jump from 0 to
    5,000,000 stored five million numbers in one call (a reset or a corrupt
    value, not five million lost messages) and now raises ``ValueError``.
    """

    def __init__(self, *, max_gap: int = 100_000) -> None:
        self._streams: Dict[str, Dict[str, Any]] = {}
        self._max_gap = int(max_gap)

    def _state(self, stream_id: str) -> Dict[str, Any]:
        return self._streams.setdefault(
            stream_id, {"first": None, "high": None, "gaps": set(), "early": set()})

    @staticmethod
    def _is_duplicate(state: Dict[str, Any], seq: int) -> bool:
        if state["high"] is None:
            return False
        if seq < state["first"]:
            return seq in state["early"]
        return seq <= state["high"] and seq not in state["gaps"]

    def observe(self, stream_id: str, seq: int) -> Dict[str, Any]:
        """Record ``seq`` for ``stream_id``; return its classification.

        Returns ``{status, seq, missing}`` where status is ``ok`` (next in
        order), ``duplicate`` (seen before), ``gap`` (skipped ahead), or
        ``reorder`` (a late earlier number). ``missing`` is the outstanding
        gap list.
        """
        state = self._state(stream_id)
        seq = int(seq)
        if self._is_duplicate(state, seq):
            return {"status": "duplicate", "seq": seq,
                    "missing": sorted(state["gaps"])}
        status = self._advance(state, seq)
        return {"status": status, "seq": seq, "missing": sorted(state["gaps"])}

    def _advance(self, state: Dict[str, Any], seq: int) -> str:
        high = state["high"]
        if high is None:
            state["first"] = state["high"] = seq
            return "ok"
        if seq == high + 1:
            state["high"] = seq
            return "ok"
        if seq > high + 1:
            outstanding = len(state["gaps"]) + seq - high - 1
            if outstanding > self._max_gap:
                raise ValueError(
                    f"sequence jumped from {high} to {seq}: {outstanding} missing "
                    f"numbers exceed max_gap={self._max_gap}")
            state["gaps"].update(range(high + 1, seq))
            state["high"] = seq
            return "gap"
        if seq < state["first"]:
            state["early"].add(seq)
        state["gaps"].discard(seq)          # a late arrival filling a hole
        return "reorder"

    def gaps(self, stream_id: str) -> List[int]:
        """The outstanding missing sequence numbers for ``stream_id``."""
        return sorted(self._state(stream_id)["gaps"])

    def high_water(self, stream_id: str) -> Any:
        """The highest sequence number observed for ``stream_id`` (or ``None``)."""
        return self._state(stream_id)["high"]
