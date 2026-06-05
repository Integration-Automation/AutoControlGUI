"""Tests for the WinUSB / IOKit backends + the per-OS factory."""
import platform

import pytest

from je_auto_control.utils.usb.passthrough import (
    UsbBackend, default_passthrough_backend,
)
from je_auto_control.utils.usb.passthrough.winusb_backend import WinusbBackend
from je_auto_control.utils.usb.passthrough.iokit_backend import IokitBackend


_IS_WINDOWS = platform.system() == "Windows"
_IS_DARWIN = platform.system() == "Darwin"
_IS_LINUX = platform.system() == "Linux"


# ---------------------------------------------------------------------------
# WinusbBackend
# ---------------------------------------------------------------------------


def test_winusb_construct_rejects_non_windows():
    if _IS_WINDOWS:
        pytest.skip("running on Windows; cross-platform reject path covered elsewhere")
    with pytest.raises(RuntimeError) as exc_info:
        WinusbBackend()
    assert "Windows" in str(exc_info.value)


@pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only path")
def test_winusb_list_returns_a_list_without_crashing():
    """SetupAPI walks cleanly even when no WinUSB-bound device is present
    (typical Windows host with no Zadig-installed driver)."""
    backend = WinusbBackend()
    result = backend.list()
    assert isinstance(result, list)
    # Every entry — if any — has the contract-mandated fields.
    for device in result:
        assert isinstance(device.vendor_id, str)
        assert isinstance(device.product_id, str)
        assert len(device.vendor_id) == 4
        assert len(device.product_id) == 4


@pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only path")
def test_winusb_open_against_definitely_absent_vid_pid_raises():
    """No real device should match these IDs — open() raises RuntimeError,
    not NotImplementedError, confirming the ctypes path is wired."""
    backend = WinusbBackend()
    with pytest.raises(RuntimeError) as exc_info:
        backend.open(vendor_id="dead", product_id="beef")
    assert "no device matches" in str(exc_info.value).lower()


@pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only path")
def test_winusb_dlls_loaded():
    """Construction primes the lazy DLL bindings; subsequent calls
    should not re-error on import."""
    from je_auto_control.utils.usb.passthrough import winusb_backend as wb
    WinusbBackend()
    assert wb._setupapi is not None
    assert wb._winusb is not None
    assert wb._kernel32 is not None
    # SetupDiGetClassDevsW signature was bound.
    assert wb._setupapi.SetupDiGetClassDevsW.restype is not None


# ---------------------------------------------------------------------------
# IokitBackend
# ---------------------------------------------------------------------------


def test_iokit_construct_rejects_non_darwin():
    if _IS_DARWIN:
        pytest.skip("running on macOS; cross-platform reject path covered elsewhere")
    with pytest.raises(RuntimeError) as exc_info:
        IokitBackend()
    assert "macOS" in str(exc_info.value) or "Darwin" in str(exc_info.value)


@pytest.mark.skipif(not _IS_DARWIN, reason="Darwin-only path")
def test_iokit_list_returns_a_list_without_crashing():
    """Native IOKit enumeration walks the registry and returns a list
    (possibly empty) with contract-mandated 4-hex-digit VID/PID."""
    backend = IokitBackend()
    result = backend.list()
    assert isinstance(result, list)
    for device in result:
        assert isinstance(device.vendor_id, str)
        assert isinstance(device.product_id, str)
        assert len(device.vendor_id) == 4
        assert len(device.product_id) == 4


@pytest.mark.skipif(not _IS_DARWIN, reason="Darwin-only path")
def test_iokit_open_absent_device_raises_runtime_error():
    """open() delegates the claim to libusb; an absent VID/PID raises
    RuntimeError (or a clear message if libusb isn't installed)."""
    backend = IokitBackend()
    with pytest.raises(RuntimeError):
        backend.open(vendor_id="dead", product_id="beef")


# ---------------------------------------------------------------------------
# default_passthrough_backend factory
# ---------------------------------------------------------------------------


def test_factory_returns_usb_backend_for_current_os():
    """The factory picks a backend for whichever OS the test runs on.

    Construction can fail if the platform's USB libs are absent (e.g.
    libusb on a headless Linux CI box) — that surfaces as RuntimeError,
    which is itself the documented contract.
    """
    try:
        backend = default_passthrough_backend()
    except RuntimeError:
        pytest.skip("platform USB backend dependencies unavailable here")
    assert isinstance(backend, UsbBackend)


@pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only path")
def test_factory_picks_winusb_on_windows():
    assert isinstance(default_passthrough_backend(), WinusbBackend)


@pytest.mark.skipif(not _IS_DARWIN, reason="Darwin-only path")
def test_factory_picks_iokit_on_macos():
    assert isinstance(default_passthrough_backend(), IokitBackend)
