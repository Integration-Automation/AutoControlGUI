"""Headless tests for platform identification. No Qt.

``sys.platform`` was compared against literal lists in over a hundred places,
and every one named win32/cygwin/msys, darwin and linux/linux2 — so an
operating system that is none of those and still runs X11 was a hundred
separate places to be wrong. These pin the one place that decides now.

The real FreeBSD check is the ``freebsd`` job in ``platform-smoke.yml``, which
boots a VM and imports the X11 backend on it; what is worth pinning here is
the classification itself, which is pure and can be checked from anywhere.
"""
import pytest

from je_auto_control.utils.platform_id import (
    current_family, is_bsd, is_macos, is_windows, is_x11_unix,
)


@pytest.mark.parametrize("platform,family", [
    ("win32", "windows"), ("cygwin", "windows"), ("msys", "windows"),
    ("darwin", "macos"),
    ("linux", "linux"), ("linux2", "linux"),
    ("freebsd14", "bsd"), ("freebsd13", "bsd"),
    ("openbsd7", "bsd"), ("netbsd10", "bsd"), ("dragonfly6", "bsd"),
])
def test_families_are_classified(platform, family):
    assert current_family(platform) == family


def test_an_unknown_platform_keeps_its_own_name():
    """Better a name the reader can look up than a wrong family."""
    assert current_family("haiku1") == "haiku1"
    assert not is_x11_unix("haiku1")


@pytest.mark.parametrize("platform", [
    "freebsd14", "openbsd7", "netbsd10", "dragonfly6"])
def test_the_bsds_are_x11_unixes(platform):
    """What the X11 backend needs is an X server and python-Xlib.

    Neither is Linux-specific, and a BSD desktop is an ordinary X11 desktop,
    so the guards ask this rather than asking whether the kernel is Linux.
    """
    assert is_bsd(platform)
    assert is_x11_unix(platform)
    assert not is_windows(platform)
    assert not is_macos(platform)


def test_the_bsd_version_suffix_does_not_matter():
    """sys.platform carries the major version there — freebsd14, not freebsd.

    An equality check against "freebsd" matches no real system at all, which
    is the trap this prefix match exists to avoid.
    """
    assert is_bsd("freebsd")
    assert is_bsd("freebsd15")
    # Prefix, not equality: matching "freebsd" exactly matches no real
    # system. Python's own porting guidance says to compare this way.
    assert not is_bsd("linux")
    assert not is_bsd("darwin")


def test_macos_is_not_an_x11_unix():
    """It is a unix, but its backend is Quartz — the distinction that matters."""
    assert is_macos("darwin")
    assert not is_x11_unix("darwin")


def test_the_helpers_default_to_this_interpreter():
    """Called with no argument they answer about the running platform."""
    families = {is_windows(), is_macos(), is_x11_unix()}
    assert True in families, "this platform matches none of the families"
