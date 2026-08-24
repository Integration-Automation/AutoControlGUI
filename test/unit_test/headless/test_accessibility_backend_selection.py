"""Which accessibility backend a platform gets, and what the rest refuse.

The seam is the same shape as the window-management one -- abstract base,
three implementations, a null fallback carrying a reason -- and it had the
same hole: the selector only ever ran its own platform's arm, so two of the
three branches were dead on every square, along with the base class's whole
refusal surface.

Two things are worth stating in a test rather than in a comment:

* **The reason has to name the *right* missing thing.** These are the
  messages an operator reads when `ac_list_accessibility_elements` comes back
  empty, and each platform fails for a different reason: a missing pip
  package on Windows, a missing framework on macOS, and on Linux a *bus* that
  may be absent or merely unbridged -- which is why that one names
  at-spi2-core and the toolkit bridge in the same breath.
* **The base refuses rather than answering falsely.** Thirty-odd control
  patterns exist because UIA has them; AT-SPI and AX have a fraction. A
  backend that returned `None` or `False` for the rest would be indis-
  tinguishable from "the control is not there", and a caller cannot recover
  from that. Every one of them raises instead.

The macOS backend is exercised here too, through the pyobjc stub, which is
what lets all of this run on every square rather than only on Darwin.
"""
from __future__ import annotations

import sys
import types

import pytest

from headless import _pyobjc_stub as objc_stub
from je_auto_control.utils.accessibility import backends as backends_mod
from je_auto_control.utils.accessibility.backends import (
    NullAccessibilityBackend, get_backend, reset_backend_cache,
)
from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityNotAvailableError,
)


@pytest.fixture(autouse=True)
def clean_cache():
    reset_backend_cache()
    yield
    reset_backend_cache()


@pytest.fixture
def on_platform(monkeypatch):
    def _set(name: str):
        monkeypatch.setattr(backends_mod.sys, "platform", name)
    return _set


def _stub_module(monkeypatch, name: str, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


# --- selection ----------------------------------------------------------------

def test_windows_with_comtypes_selects_the_uia_backend(on_platform,
                                                       monkeypatch):
    on_platform("win32")
    monkeypatch.setattr(
        "je_auto_control.utils.accessibility.backends.windows_backend"
        "._is_available", lambda: True)
    assert get_backend().name == "windows-uia"


def test_windows_without_comtypes_gets_a_refusal_naming_it(on_platform,
                                                           monkeypatch):
    on_platform("win32")
    monkeypatch.setattr(
        "je_auto_control.utils.accessibility.backends.windows_backend"
        "._is_available", lambda: False)
    backend = get_backend()
    assert isinstance(backend, NullAccessibilityBackend)
    with pytest.raises(AccessibilityNotAvailableError, match="comtypes"):
        backend.list_elements()


def test_a_mac_with_pyobjc_selects_the_ax_backend(on_platform, monkeypatch):
    on_platform("darwin")
    objc_stub.install(monkeypatch, objc_stub.World())
    _stub_module(monkeypatch, "ApplicationServices")
    assert get_backend().name == "macos-ax"


def test_a_mac_without_pyobjc_gets_a_refusal_naming_it(on_platform,
                                                       monkeypatch):
    on_platform("darwin")
    monkeypatch.setitem(sys.modules, "ApplicationServices", None)
    backend = get_backend()
    with pytest.raises(AccessibilityNotAvailableError, match="pyobjc"):
        backend.list_elements()


def test_a_linux_session_with_a_bus_selects_the_atspi_backend(on_platform,
                                                              monkeypatch):
    on_platform("linux")
    monkeypatch.setattr(
        "je_auto_control.utils.accessibility.backends.linux_backend"
        "._is_available", lambda: True)
    assert get_backend().name == "linux-atspi"


def test_a_linux_session_with_no_bus_names_both_ways_it_can_be_missing(
        on_platform, monkeypatch):
    # AT-SPI is a bus, not a library, so "not installed" and "installed but
    # nothing is bridged to it" look identical from here.
    on_platform("linux")
    monkeypatch.setattr(
        "je_auto_control.utils.accessibility.backends.linux_backend"
        "._is_available", lambda: False)
    backend = get_backend()
    with pytest.raises(AccessibilityNotAvailableError) as caught:
        backend.list_elements()
    message = str(caught.value)
    assert "at-spi2-core" in message
    assert "atk-bridge" in message


def test_an_unknown_platform_gets_a_refusal_naming_it(on_platform):
    on_platform("sunos5")
    with pytest.raises(AccessibilityNotAvailableError, match="sunos5"):
        get_backend().list_elements()


def test_the_choice_is_made_once_and_cached(on_platform):
    on_platform("sunos5")
    assert get_backend() is get_backend()


def test_resetting_the_cache_re_detects(on_platform):
    on_platform("sunos5")
    first = get_backend()
    reset_backend_cache()
    assert get_backend() is not first


# --- what the base class refuses ----------------------------------------------

_REFUSALS = [
    ("get_value", lambda b: b.get_value()),
    ("set_value", lambda b: b.set_value("x")),
    ("invoke", lambda b: b.invoke()),
    ("toggle", lambda b: b.toggle()),
    ("read_table", lambda b: b.read_table()),
    ("expand", lambda b: b.expand()),
    ("collapse", lambda b: b.collapse()),
    ("expand_state", lambda b: b.expand_state()),
    ("select_item", lambda b: b.select_item()),
    ("get_range", lambda b: b.get_range()),
    ("set_range_value", lambda b: b.set_range_value(1.0)),
    ("scroll_into_view", lambda b: b.scroll_into_view()),
    ("document_text", lambda b: b.document_text()),
    ("selected_text", lambda b: b.selected_text()),
    ("visible_text", lambda b: b.visible_text()),
    ("find_text", lambda b: b.find_text("x")),
    ("select_text", lambda b: b.select_text("x")),
    ("text_attributes", lambda b: b.text_attributes()),
    ("set_focus", lambda b: b.set_focus()),
    ("find_virtual_item", lambda b: b.find_virtual_item("x")),
    ("get_properties", lambda b: b.get_properties()),
    ("get_state", lambda b: b.get_state()),
    ("get_table_headers", lambda b: b.get_table_headers()),
    ("get_grid_cell", lambda b: b.get_grid_cell(0, 0)),
    ("move_element", lambda b: b.move_element(1.0, 2.0)),
    ("resize_element", lambda b: b.resize_element(1.0, 2.0)),
    ("set_window_state", lambda b: b.set_window_state("normal")),
    ("window_interaction_state", lambda b: b.window_interaction_state()),
    ("legacy_info", lambda b: b.legacy_info()),
    ("legacy_default_action", lambda b: b.legacy_default_action()),
    ("get_selection", lambda b: b.get_selection()),
    ("list_views", lambda b: b.list_views()),
    ("set_view", lambda b: b.set_view("Details")),
    ("wait_for_focus_change", lambda b: b.wait_for_focus_change(0.1)),
]


@pytest.mark.parametrize("operation,call",
                         _REFUSALS, ids=[name for name, _ in _REFUSALS])
def test_an_unimplemented_pattern_says_which_one_and_whose(operation, call):
    # "This backend cannot do it" and "the control is not there" are
    # different answers, and a caller that cannot tell them apart retries
    # forever. The message carries both halves.
    backend = AccessibilityBackend()
    with pytest.raises(AccessibilityNotAvailableError) as caught:
        call(backend)
    assert operation in str(caught.value)
    assert backend.name in str(caught.value)


def test_the_base_class_has_no_listing_of_its_own():
    with pytest.raises(NotImplementedError):
        AccessibilityBackend().list_elements()


def test_the_null_backend_refuses_to_list_with_its_reason():
    with pytest.raises(AccessibilityNotAvailableError, match="no display"):
        NullAccessibilityBackend("no display").list_elements()


def test_a_null_backend_with_no_reason_still_says_something():
    with pytest.raises(AccessibilityNotAvailableError) as caught:
        NullAccessibilityBackend().list_elements()
    assert str(caught.value)
