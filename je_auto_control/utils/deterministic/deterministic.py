"""Deterministic run controls — seeded RNG and a frozen wall clock.

Time and randomness are two of the top causes of flaky automation. This
module pins both for the duration of a ``with`` block and records the
choices so a run can be reproduced exactly::

    from je_auto_control import DeterministicRun

    with DeterministicRun(seed=42, freeze_time=1_750_000_000.0) as run:
        ...                      # random.* reproducible; time.time() frozen
    manifest = run.manifest()    # {"seed": 42, "freeze_time": 1750000000.0}

Scope (pure standard library — no ``freezegun`` dependency):

* **RNG** — seeds the global :mod:`random` generator and restores its
  state on exit.
* **Wall clock** — patches ``time.time`` / ``time.time_ns`` to a fixed
  instant. ``time.monotonic`` is deliberately left alone so duration
  measurements and timeouts keep working.

Imports no ``PySide6``.
"""
import random
from typing import Any, Dict, Literal, Optional
from unittest import mock

_UNSET = object()


def seed_everything(seed: int) -> int:
    """Seed the global :mod:`random` generator (and numpy if importable).

    Returns the seed, for recording in run artifacts.
    """
    random.seed(int(seed))
    try:  # numpy is optional; seed it too when present
        import numpy
        numpy.random.seed(int(seed) % (2 ** 32))
    except ImportError:
        pass
    return int(seed)


class DeterministicRun:
    """Context manager pinning RNG seed and (optionally) the wall clock."""

    def __init__(self, seed: int = 0,
                 freeze_time: Optional[float] = None) -> None:
        self._seed = int(seed)
        self._freeze_time = (None if freeze_time is None
                             else float(freeze_time))
        self._rng_state: Any = _UNSET
        self._patches: list = []

    @property
    def seed(self) -> int:
        """The RNG seed pinned for this run."""
        return self._seed

    @property
    def frozen(self) -> Optional[float]:
        """The frozen wall-clock instant (epoch seconds) or ``None``."""
        return self._freeze_time

    def manifest(self) -> Dict[str, Any]:
        """Return the run's deterministic settings (for artifacts/replay)."""
        return {"seed": self._seed, "freeze_time": self._freeze_time}

    def _freeze_clock(self) -> None:
        instant = self._freeze_time
        if instant is None:
            return
        time_patch = mock.patch("time.time", return_value=instant)
        ns_patch = mock.patch("time.time_ns", return_value=int(instant * 1e9))
        for patch in (time_patch, ns_patch):
            patch.start()
            self._patches.append(patch)

    def __enter__(self) -> "DeterministicRun":
        self._rng_state = random.getstate()
        seed_everything(self._seed)
        if self._freeze_time is not None:
            self._freeze_clock()
        return self

    def __exit__(self, *exc: Any) -> Literal[False]:
        while self._patches:
            self._patches.pop().stop()
        if self._rng_state is not _UNSET:
            random.setstate(self._rng_state)
            self._rng_state = _UNSET
        return False
