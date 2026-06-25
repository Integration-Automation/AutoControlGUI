"""Read and control the system master volume and mute state.

Unattended runs often need to set a known audio baseline — mute before a noisy
batch, restore a level afterwards, or assert the current volume — but the
framework only had the blind media-key steps (``volume up`` / ``down`` nudge by
an unknown amount with no read-back). ``system_volume`` adds absolute,
read-backable control of the default output device:

* :func:`get_volume` / :func:`set_volume` / :func:`change_volume` read and write
  the master level as an integer percent ``0..100``.
* :func:`is_muted` / :func:`set_mute` / :func:`mute` / :func:`unmute` /
  :func:`toggle_mute` read and write the mute flag.

All logic (clamping, percent <-> scalar conversion, toggle) is pure and runs
through an injectable :class:`VolumeDriver` seam, so it is fully testable without
an audio device. The default driver drives the Windows Core Audio
``IAudioEndpointVolume`` interface through the optional ``pycaw`` dependency
(``pip install je_auto_control[audio]``); on a platform / install without it the
default driver raises a clear error telling the caller to pass ``driver=``.

Imports no ``PySide6``.
"""
import sys
from typing import Optional, Protocol

# A normalized master-volume scalar runs 0.0 (silent) .. 1.0 (full).
_MIN_SCALAR = 0.0
_MAX_SCALAR = 1.0
_PERCENT_MAX = 100


class VolumeDriver(Protocol):
    """The OS seam used by every public function.

    Implementations expose the master output volume as a ``0.0 .. 1.0`` scalar
    and a boolean mute flag. Pass a fake implementing these four methods to test
    the pure logic without an audio device.
    """

    def get_scalar(self) -> float:
        """Return the current master volume as a ``0.0 .. 1.0`` scalar."""

    def set_scalar(self, scalar: float) -> None:
        """Set the master volume from a ``0.0 .. 1.0`` scalar."""

    def get_mute(self) -> bool:
        """Return whether the master output is muted."""

    def set_mute(self, muted: bool) -> None:
        """Mute or unmute the master output."""


def clamp_percent(level: float) -> int:
    """Clamp ``level`` to an integer percent in ``[0, 100]`` (pure)."""
    rounded = int(round(float(level)))
    return max(0, min(_PERCENT_MAX, rounded))


def percent_to_scalar(level: float) -> float:
    """Convert a ``0..100`` percent to a clamped ``0.0 .. 1.0`` scalar (pure)."""
    return clamp_percent(level) / float(_PERCENT_MAX)


def scalar_to_percent(scalar: float) -> int:
    """Convert a ``0.0 .. 1.0`` scalar to a clamped integer percent (pure)."""
    bounded = max(_MIN_SCALAR, min(_MAX_SCALAR, float(scalar)))
    return clamp_percent(bounded * _PERCENT_MAX)


def _resolve(driver: Optional[VolumeDriver]) -> VolumeDriver:
    """Return the supplied driver, or the default OS driver."""
    return driver if driver is not None else _default_driver()


def get_volume(*, driver: Optional[VolumeDriver] = None) -> int:
    """Return the system master volume as an integer percent ``0..100``.

    Pass ``driver`` (any :class:`VolumeDriver`) to read from a fake in tests; the
    default queries the OS through ``pycaw`` (Windows).
    """
    return scalar_to_percent(_resolve(driver).get_scalar())


def set_volume(level: float, *, driver: Optional[VolumeDriver] = None) -> int:
    """Set the master volume to ``level`` percent; return the applied percent.

    ``level`` is clamped to ``[0, 100]`` before it is applied.
    """
    target = clamp_percent(level)
    _resolve(driver).set_scalar(percent_to_scalar(target))
    return target


def change_volume(delta: float, *,
                  driver: Optional[VolumeDriver] = None) -> int:
    """Add ``delta`` percent to the current volume; return the applied percent.

    The result is clamped to ``[0, 100]``. ``delta`` may be negative.
    """
    source = _resolve(driver)
    current = scalar_to_percent(source.get_scalar())
    target = clamp_percent(current + float(delta))
    source.set_scalar(percent_to_scalar(target))
    return target


def is_muted(*, driver: Optional[VolumeDriver] = None) -> bool:
    """Return whether the master output is currently muted."""
    return bool(_resolve(driver).get_mute())


def set_mute(muted: bool, *, driver: Optional[VolumeDriver] = None) -> bool:
    """Set the mute flag to ``muted``; return the new mute state."""
    state = bool(muted)
    _resolve(driver).set_mute(state)
    return state


def mute(*, driver: Optional[VolumeDriver] = None) -> bool:
    """Mute the master output; return ``True``."""
    return set_mute(True, driver=driver)


def unmute(*, driver: Optional[VolumeDriver] = None) -> bool:
    """Unmute the master output; return ``False``."""
    return set_mute(False, driver=driver)


def toggle_mute(*, driver: Optional[VolumeDriver] = None) -> bool:
    """Flip the mute flag; return the new mute state."""
    source = _resolve(driver)
    new_state = not bool(source.get_mute())
    source.set_mute(new_state)
    return new_state


class _PycawDriver:
    """Default :class:`VolumeDriver` over Windows Core Audio via ``pycaw``."""

    def __init__(self) -> None:
        """Activate the default-output ``IAudioEndpointVolume`` interface."""
        from ctypes import POINTER, cast  # local: optional Windows path
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        speakers = AudioUtilities.GetSpeakers()
        interface = speakers.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self._volume = cast(interface, POINTER(IAudioEndpointVolume))

    def get_scalar(self) -> float:
        """Read the master volume scalar from Core Audio."""
        return float(self._volume.GetMasterVolumeLevelScalar())

    def set_scalar(self, scalar: float) -> None:
        """Write the master volume scalar to Core Audio."""
        self._volume.SetMasterVolumeLevelScalar(float(scalar), None)

    def get_mute(self) -> bool:
        """Read the master mute flag from Core Audio."""
        return bool(self._volume.GetMute())

    def set_mute(self, muted: bool) -> None:
        """Write the master mute flag to Core Audio."""
        self._volume.SetMute(bool(muted), None)


def _default_driver() -> VolumeDriver:
    """Return the OS volume driver, or raise if unavailable.

    Uses Windows Core Audio through the optional ``pycaw`` dependency. Raises
    ``RuntimeError`` on a non-Windows platform or when ``pycaw`` is not
    installed, instructing the caller to pass ``driver=``.
    """
    if not sys.platform.startswith("win"):
        raise RuntimeError(
            "system volume has no OS driver on this platform; pass driver=")
    try:
        return _PycawDriver()
    except ImportError as exc:
        raise RuntimeError(
            "system volume needs the 'pycaw' package on Windows "
            "(pip install je_auto_control[audio]); or pass driver=") from exc
