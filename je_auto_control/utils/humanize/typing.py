"""Human-like typing: per-character delays with jitter + occasional pauses.

The delay sequence (:func:`humanized_key_delays`) is pure and
deterministic given a seed, so it is unit-testable;
:func:`type_text_humanized` walks it through the keyboard wrapper. The
typing counterpart of :mod:`je_auto_control.utils.humanize.motion`.
"""
import random
import time
from typing import Callable, List, Optional


def humanized_key_delays(text: str, *, base_delay: float = 0.05,
                         jitter: float = 0.04, pause_chance: float = 0.0,
                         pause_delay: float = 0.3,
                         seed: Optional[int] = None) -> List[float]:
    """Return a per-character delay (seconds) list for typing ``text``.

    Each delay is ``base_delay`` ± up to ``jitter`` (clamped at 0), with a
    ``pause_chance`` probability of an extra ``pause_delay`` (a human
    pausing to think). Deterministic when ``seed`` is set.
    """
    rng = random.Random(seed)
    delays: List[float] = []
    for _ in text:
        delay = max(0.0, base_delay + rng.uniform(-jitter, jitter))
        if pause_chance and rng.random() < pause_chance:
            delay += pause_delay
        delays.append(delay)
    return delays


def _default_typer(char: str) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import write
    write(char)


def type_text_humanized(text: str, *, base_delay: float = 0.05,
                        jitter: float = 0.04, pause_chance: float = 0.0,
                        seed: Optional[int] = None,
                        typer: Optional[Callable[[str], None]] = None,
                        sleep: Callable[[float], None] = time.sleep
                        ) -> List[float]:
    """Type ``text`` character-by-character with humanized inter-key delays.

    Returns the delays used. ``typer`` / ``sleep`` are injectable for tests.
    """
    delays = humanized_key_delays(
        text, base_delay=base_delay, jitter=jitter,
        pause_chance=pause_chance, seed=seed,
    )
    write = typer or _default_typer
    for char, delay in zip(text, delays):
        write(char)
        if delay:
            sleep(delay)
    return delays
