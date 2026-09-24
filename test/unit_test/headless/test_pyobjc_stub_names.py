"""Hold the pyobjc stub to the frameworks it stands in for.

`_pyobjc_stub.py` lets the macOS backends be tested on all nine CI squares by
shadowing `Quartz`, `AppKit` and `ApplicationServices` in `sys.modules`. The
risk that buys is a stub that answers for a name the real framework does not
have -- a test that passes everywhere and a backend that raises
`AttributeError` on the one platform it exists for.

pyobjc is a hard dependency on Darwin, so on the macOS squares the genuine
frameworks are installed and every name the stub declares is looked up on
them. Elsewhere there is nothing to compare against and these skip.

Names, not values. Every constant in the stub is either a key into an info
dictionary the stub itself builds or an opaque token handed back to a
function the stub itself provides, so none of their numbers reaches any
arithmetic in the code under test. What matters is that the backend is
spelling real API.
"""
from __future__ import annotations

import pytest

from headless import _pyobjc_stub as objc_stub

pytest.importorskip("Quartz", reason="pyobjc is a macOS-only dependency")


@pytest.mark.parametrize("name", sorted(objc_stub.QUARTZ_NAMES))
def test_every_quartz_name_the_stub_answers_for_exists(name):
    import Quartz
    assert hasattr(Quartz, name), f"Quartz.{name}"


@pytest.mark.parametrize("name", sorted(objc_stub.APPKIT_NAMES))
def test_every_appkit_name_the_stub_answers_for_exists(name):
    import AppKit
    assert hasattr(AppKit, name), f"AppKit.{name}"


@pytest.mark.parametrize("name", sorted(objc_stub.AX_NAMES))
def test_every_accessibility_name_the_stub_answers_for_exists(name):
    import ApplicationServices
    assert hasattr(ApplicationServices, name), f"ApplicationServices.{name}"


def test_the_window_list_options_are_the_flags_the_backend_composes():
    # These two are the only Quartz numbers the backend does arithmetic on:
    # it ORs them into the argument of CGWindowListCopyWindowInfo.
    import Quartz
    assert Quartz.kCGWindowListOptionOnScreenOnly == 1
    assert Quartz.kCGWindowListExcludeDesktopElements == 16
    assert Quartz.kCGNullWindowID == 0
