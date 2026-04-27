"""Tests for the WinUSB / IOKit backend skeletons (round 42)."""
import platform

import pytest

from je_auto_control.utils.usb.passthrough.winusb_backend import WinusbBackend
from je_auto_control.utils.usb.passthrough.iokit_backend import IokitBackend


_IS_WINDOWS = platform.system() == "Windows"
_IS_DARWIN = platform.system() == "Darwin"


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
def test_iokit_list_raises_not_implemented():
    backend = IokitBackend()
    with pytest.raises(NotImplementedError):
        backend.list()


@pytest.mark.skipif(not _IS_DARWIN, reason="Darwin-only path")
def test_iokit_open_raises_not_implemented():
    backend = IokitBackend()
    with pytest.raises(NotImplementedError):
        backend.open(vendor_id="1050", product_id="0407")
