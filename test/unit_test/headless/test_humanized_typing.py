"""Tests for human-like typing (jittered per-key delays)."""
from je_auto_control.utils.humanize.typing import (
    humanized_key_delays, type_text_humanized,
)


def test_delays_one_per_character_and_deterministic():
    first = humanized_key_delays("hello", seed=1)
    second = humanized_key_delays("hello", seed=1)
    assert len(first) == 5
    assert first == second
    assert all(delay >= 0.0 for delay in first)


def test_delays_stay_within_jitter_band_without_pauses():
    delays = humanized_key_delays("xxxx", base_delay=0.1, jitter=0.05,
                                  pause_chance=0.0, seed=2)
    assert all(0.05 <= delay <= 0.15 for delay in delays)


def test_pauses_add_extra_delay():
    delays = humanized_key_delays("ab", base_delay=0.1, jitter=0.0,
                                  pause_chance=1.0, pause_delay=0.5, seed=3)
    assert all(delay >= 0.5 for delay in delays)  # every key pauses


def test_type_text_humanized_types_each_char():
    typed = []
    slept = []
    delays = type_text_humanized(
        "hi", seed=1, typer=typed.append, sleep=slept.append,
    )
    assert typed == ["h", "i"]
    assert len(delays) == 2
    assert len(slept) == 2  # one sleep per character
