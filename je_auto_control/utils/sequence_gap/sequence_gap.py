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
    """Tracks per-stream sequence numbers and classifies each observation."""

    def __init__(self) -> None:
        self._streams: Dict[str, Dict[str, Any]] = {}

    def _state(self, stream_id: str) -> Dict[str, Any]:
        return self._streams.setdefault(
            stream_id, {"high": None, "seen": set(), "gaps": set()})

    def observe(self, stream_id: str, seq: int) -> Dict[str, Any]:
        """Record ``seq`` for ``stream_id``; return its classification.

        Returns ``{status, seq, missing}`` where status is ``ok`` (next in
        order), ``duplicate`` (seen before), ``gap`` (skipped ahead), or
        ``reorder`` (a late earlier number). ``missing`` is the outstanding
        gap list.
        """
        state = self._state(stream_id)
        seq = int(seq)
        if seq in state["seen"]:
            return {"status": "duplicate", "seq": seq,
                    "missing": sorted(state["gaps"])}
        state["seen"].add(seq)
        status = self._advance(state, seq)
        return {"status": status, "seq": seq, "missing": sorted(state["gaps"])}

    @staticmethod
    def _advance(state: Dict[str, Any], seq: int) -> str:
        high = state["high"]
        if high is None or seq == high + 1:
            state["high"] = seq
            return "ok"
        if seq > high + 1:
            state["gaps"].update(range(high + 1, seq))
            state["high"] = seq
            return "gap"
        state["gaps"].discard(seq)          # a late arrival filling a hole
        return "reorder"

    def gaps(self, stream_id: str) -> List[int]:
        """The outstanding missing sequence numbers for ``stream_id``."""
        return sorted(self._state(stream_id)["gaps"])

    def high_water(self, stream_id: str) -> Any:
        """The highest sequence number observed for ``stream_id`` (or ``None``)."""
        return self._state(stream_id)["high"]
