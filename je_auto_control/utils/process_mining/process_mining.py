"""Mine a recorded action log for repetitive, automatable sequences.

Enterprise RPA suites *discover* what to automate by mining recorded desktop
actions for frequent, repeatable sub-sequences. AutoControl records rich action
logs but never analysed them; this turns a log into a ranked list of automation
candidates: it counts repeated command n-grams, builds a directly-follows graph,
and scores candidates by how often and how long the repeated run is.

Operates on the project's action-list shape — each step is either a
``["AC_name", {...}]`` pair or a ``{"command": "AC_name", ...}`` mapping. Pure
standard library (``collections``); imports no ``PySide6``.
"""
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class SequencePattern:
    """A repeated command sub-sequence and how often it occurs."""

    actions: Tuple[str, ...]
    count: int


@dataclass(frozen=True)
class Candidate:
    """An automation candidate: a pattern with a priority score."""

    pattern: SequencePattern
    score: int


@dataclass(frozen=True)
class MiningReport:
    """The result of mining an action log."""

    total_actions: int
    patterns: List[SequencePattern]
    candidates: List[Candidate]


def _command_name(action: Any) -> str:
    if isinstance(action, dict):
        return str(action.get("command", action.get("name", "")))
    if isinstance(action, (list, tuple)) and action:
        return str(action[0])
    return str(action)


def _command_names(actions: Sequence[Any]) -> List[str]:
    return [_command_name(action) for action in actions]


def find_repeated_sequences(actions: Sequence[Any], *, min_len: int = 2,
                            max_len: int = 5, min_count: int = 3
                            ) -> List[SequencePattern]:
    """Return command n-grams (``min_len``..``max_len``) seen >= ``min_count``."""
    names = _command_names(actions)
    patterns: List[SequencePattern] = []
    for length in range(min_len, max_len + 1):
        if length > len(names):
            break
        counter: Counter = Counter(
            tuple(names[i:i + length])
            for i in range(len(names) - length + 1))
        patterns.extend(
            SequencePattern(gram, count)
            for gram, count in counter.items() if count >= min_count)
    patterns.sort(key=lambda p: (p.count * len(p.actions)), reverse=True)
    return patterns


def directly_follows(actions: Sequence[Any]) -> Dict[Tuple[str, str], int]:
    """Return the directly-follows edge counts of the command flow."""
    names = _command_names(actions)
    edges: Counter = Counter(
        (names[i], names[i + 1]) for i in range(len(names) - 1))
    return dict(edges)


def rank_automation_candidates(report: MiningReport) -> List[Candidate]:
    """Score patterns by ``count * length`` (more/longer repeats rank higher)."""
    candidates = [
        Candidate(pattern, pattern.count * len(pattern.actions))
        for pattern in report.patterns
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def mine_action_log(actions: Sequence[Any], *, min_len: int = 2,
                    max_len: int = 5, min_count: int = 3) -> MiningReport:
    """Mine ``actions`` into a report of patterns and ranked candidates."""
    patterns = find_repeated_sequences(
        actions, min_len=min_len, max_len=max_len, min_count=min_count)
    report = MiningReport(len(actions), patterns, [])
    return MiningReport(len(actions), patterns,
                        rank_automation_candidates(report))
