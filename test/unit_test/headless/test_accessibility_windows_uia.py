"""Setting up UIAutomation, listing a desktop, and converting an element.

`backends/windows_backend.py` is the biggest single hole in this project's
coverage. It stayed one on the Windows squares as much as the others: a test
that reaches it needs a UIAutomation provider, a desktop with windows on it,
and applications willing to answer. But every `comtypes` import in the module
is inside a function and the automation object lives on the instance, so
doubles reach all of it -- from every square.

This file covers getting there and getting back: the automation object, the
listing, the search, and the conversion. The control patterns are in
`test_accessibility_windows_patterns.py`.

Three decisions in here were made against measurements, and are the kind that
get undone by a well-meaning simplification:

* **`CUIAutomation8` is asked for first.** It is the only class that hands out
  `IUIAutomation2`, which is the only way to bound how long UIA waits on an
  application's provider. A full-screen game that never answered made one
  `ElementFromHandle` block for 60 seconds; with the timeout set, 1.0 s. Only
  the *connect* step is bounded -- how long a legitimate query may take is a
  different question.
* **The listing pulls one window at a time.** A desktop-rooted walk measured
  ~61 s and cannot be interrupted once started. The budget is checked
  *before* the next window is fetched, not after, because obtaining a
  window's root element is itself a cross-process call that blocks against a
  hung application -- fetching one more root only to find the results already
  complete cost exactly that.
* **An `app_name` filter walks more than it keeps.** Most elements in a
  window belong to that window's application, so a small overscan is plenty
  -- but it is still bounded, or an unmatched filter walks an entire subtree
  to return nothing.
"""
from __future__ import annotations

import sys
import types

import pytest

from headless._uia_doubles import (
    Automation, RawElement, Rect, UiaModule, install_comtypes,
)
from je_auto_control.utils.accessibility.backends import (
    windows_backend as backend_module,
)
from je_auto_control.utils.accessibility.backends.windows_backend import (
    WindowsAccessibilityBackend, _convert_uia, _create_automation,
    _process_name, _read_properties, _safe_name,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityNotAvailableError,
)


@pytest.fixture(autouse=True)
def named_processes(monkeypatch):
    """Name a pid without asking Windows about a pid the test invented."""
    monkeypatch.setattr(backend_module, "_process_name",
                        lambda pid: f"app{pid}.exe" if pid else "")


@pytest.fixture
def backend(monkeypatch):
    """An available backend whose automation object is already built."""
    monkeypatch.setattr(backend_module, "_is_available", lambda: True)
    instance = WindowsAccessibilityBackend()
    instance._automation = Automation()
    instance._uia_module = UiaModule()
    return instance


def _element(name="", control_type=50000, rect=None, process_id=0,
             automation_id="", enabled=True, cached=False):
    return RawElement(name=name, control_type=control_type,
                      rect=rect or Rect(0, 0, 10, 20), process_id=process_id,
                      automation_id=automation_id, enabled=enabled,
                      cached=cached)


# --- availability and the automation object -----------------------------------

def test_a_windows_box_without_comtypes_refuses_and_says_how_to_fix_it(
        monkeypatch):
    monkeypatch.setattr(backend_module, "_is_available", lambda: False)
    instance = WindowsAccessibilityBackend()
    with pytest.raises(AccessibilityNotAvailableError, match="pip install"):
        instance.list_elements()


def test_the_probe_reports_whether_comtypes_imports(monkeypatch):
    install_comtypes(monkeypatch)
    assert backend_module._is_available() is True
    monkeypatch.setitem(sys.modules, "comtypes.client", None)
    assert backend_module._is_available() is False


def test_the_backend_names_the_api_it_uses(backend):
    assert backend.name == "windows-uia"


def test_the_automation_object_is_built_once_and_kept(monkeypatch):
    monkeypatch.setattr(backend_module, "_is_available", lambda: True)
    install_comtypes(monkeypatch)
    instance = WindowsAccessibilityBackend()
    first = instance._ensure_automation()
    assert instance._ensure_automation() is first


def test_a_missing_uiautomation_dll_is_reported_as_unavailable(monkeypatch):
    # The DLL is part of Windows, but a stripped image or a broken
    # registration is a real state and must not surface as an OSError.
    monkeypatch.setattr(backend_module, "_is_available", lambda: True)
    install_comtypes(monkeypatch, module_error=OSError("no such module"))
    instance = WindowsAccessibilityBackend()
    with pytest.raises(AccessibilityNotAvailableError,
                       match="UIAutomationCore.dll"):
        instance._ensure_automation()


def test_the_bounded_provider_wait_is_asked_for_first(monkeypatch):
    # CUIAutomation8 is the only class that hands out IUIAutomation2, which
    # is the only way to bound how long UIA waits on a provider.
    created = install_comtypes(monkeypatch, uia_module=UiaModule())
    automation = _create_automation(UiaModule())
    [(clsid, interface)] = created
    assert clsid == backend_module._CLSID_CUIAUTOMATION8
    assert interface == "IUIAutomation2"
    assert automation.ConnectionTimeout == 1000


def test_an_older_windows_falls_back_to_the_unbounded_class(monkeypatch):
    created = install_comtypes(monkeypatch)
    _create_automation(UiaModule(has_iuiautomation2=False))
    [(clsid, interface)] = created
    assert clsid == backend_module._CLSID_CUIAUTOMATION
    assert interface == "IUIAutomation"


def test_a_refused_iuiautomation2_falls_back_rather_than_failing(monkeypatch):
    calls = []

    def _create(clsid, interface=None):
        calls.append(clsid)
        if clsid == backend_module._CLSID_CUIAUTOMATION8:
            raise OSError("class not registered")
        return Automation()

    install_comtypes(monkeypatch, create=_create)
    assert _create_automation(UiaModule()) is not None
    assert calls == [backend_module._CLSID_CUIAUTOMATION8,
                     backend_module._CLSID_CUIAUTOMATION]


# --- listing ------------------------------------------------------------------

@pytest.fixture
def listing(monkeypatch):
    """Script `search_roots` and `walk_elements` for the listing tests."""
    state = {"roots": [], "under": {}, "walk_error": None, "budgets": [],
             "roots_pulled": 0}

    def _search_roots(automation, window_title):
        state["window_title"] = window_title
        for root in state["roots"]:
            state["roots_pulled"] += 1
            yield root

    def _walk_elements(automation, root, limit):
        state["budgets"].append(limit)
        if state["walk_error"] is not None:
            raise state["walk_error"]
        for element in state["under"].get(id(root), []):
            yield element

    monkeypatch.setattr(backend_module, "search_roots", _search_roots)
    monkeypatch.setattr(backend_module, "walk_elements", _walk_elements)
    return state


def test_a_listing_returns_the_window_and_then_its_contents(backend, listing):
    window = _element(name="Editor", process_id=7)
    child = _element(name="OK", process_id=7, cached=True)
    listing["roots"] = [window]
    listing["under"][id(window)] = [child]
    names = [e.name for e in backend.list_elements()]
    assert names == ["Editor", "OK"]


def test_a_scoped_listing_does_not_add_the_window_itself(backend, listing):
    # Searching a window's descendants does not include the window element,
    # so the unscoped walk adds it back -- and the scoped one must not, or a
    # caller asking about one window gets it twice.
    window = _element(name="Editor", process_id=7)
    child = _element(name="OK", process_id=7, cached=True)
    listing["roots"] = [window]
    listing["under"][id(window)] = [child]
    names = [e.name for e in backend.list_elements(window_title="Editor")]
    assert names == ["OK"]
    assert listing["window_title"] == "Editor"


def test_a_listing_stops_pulling_windows_once_it_has_enough(backend, listing):
    # Obtaining a window's root element is itself a cross-process call that
    # blocks against a hung application, so the budget is checked before the
    # next one is fetched rather than after.
    first, second = _element(name="one"), _element(name="two")
    listing["roots"] = [first, second]
    assert len(backend.list_elements(max_results=1)) == 1
    assert listing["roots_pulled"] == 1


def test_a_listing_asked_for_nothing_walks_nothing(backend, listing):
    listing["roots"] = [_element(name="one")]
    assert backend.list_elements(max_results=0) == []
    assert listing["roots_pulled"] == 0


def test_a_negative_maximum_is_treated_as_none(backend, listing):
    listing["roots"] = [_element(name="one")]
    assert backend.list_elements(max_results=-5) == []


def test_an_app_name_filter_keeps_only_that_application(backend, listing):
    window = _element(name="Editor", process_id=7)
    listing["roots"] = [window]
    listing["under"][id(window)] = [
        _element(name="mine", process_id=7, cached=True),
        _element(name="theirs", process_id=8, cached=True),
    ]
    names = [e.name for e in backend.list_elements(app_name="app7.exe")]
    assert names == ["Editor", "mine"]


def test_an_app_name_filter_walks_further_than_it_keeps(backend, listing):
    # Most elements in a window belong to that window's application, so the
    # overscan is small -- but an unmatched filter must still be bounded.
    window = _element(name="Editor", process_id=7)
    listing["roots"] = [window]
    backend.list_elements(app_name="app7.exe", max_results=10)
    assert listing["budgets"][0] > 10
    assert listing["budgets"][0] < 10 * 100, "bounded, not unbounded"


def test_a_filtered_window_that_does_not_match_is_not_listed(backend,
                                                             listing):
    listing["roots"] = [_element(name="Editor", process_id=8)]
    assert backend.list_elements(app_name="app7.exe") == []


def test_an_unresponsive_window_does_not_lose_the_whole_listing(backend,
                                                                listing):
    window = _element(name="Editor", process_id=7)
    listing["roots"] = [window]
    listing["walk_error"] = OSError("provider stopped responding")
    assert [e.name for e in backend.list_elements()] == ["Editor"]


def test_an_element_that_cannot_be_converted_is_skipped(backend, listing):
    window = _element(name="Editor", process_id=7)
    broken = RawElement(cached=True)
    del broken.CachedName
    listing["roots"] = [window]
    listing["under"][id(window)] = [broken,
                                    _element(name="OK", cached=True)]
    assert [e.name for e in backend.list_elements()] == ["Editor", "OK"]


def test_a_desktop_with_no_windows_lists_nothing(backend, listing):
    assert backend.list_elements() == []


def test_a_listing_stops_mid_window_once_it_has_enough(backend, listing):
    # The walk is a generator for exactly this: a window with thousands of
    # nodes costs what was asked for, not what it contains.
    window = _element(name="Editor")
    listing["roots"] = [window]
    listing["under"][id(window)] = [
        _element(name=f"c{index}", cached=True) for index in range(5)
    ]
    names = [e.name for e in backend.list_elements(max_results=2)]
    assert names == ["Editor", "c0"]


# --- searching for one control ------------------------------------------------

@pytest.fixture
def search(monkeypatch, listing):
    """The same scripting, for the `_find_raw` path."""
    return listing


def test_a_search_returns_the_first_match(backend, search):
    window = _element(name="Editor")
    wanted = _element(name="OK", cached=True)
    search["roots"] = [window]
    search["under"][id(window)] = [_element(name="Cancel", cached=True),
                                   wanted]
    assert backend._find_raw("OK", None, None, None) is wanted


def test_an_unscoped_search_can_match_the_window_itself(backend, search):
    window = _element(name="Editor")
    search["roots"] = [window]
    assert backend._find_raw("Editor", None, None, None) is window


def test_a_scoped_search_does_not_match_the_window_itself(backend, search):
    window = _element(name="Editor")
    search["roots"] = [window]
    assert backend._find_raw("Editor", None, None, None,
                             window_title="Editor") is None


def test_a_search_can_match_by_automation_id(backend, search):
    window = _element(name="Editor")
    wanted = _element(name="", automation_id="okButton", cached=True)
    search["roots"] = [window]
    search["under"][id(window)] = [wanted]
    assert backend._find_raw(None, None, None, "okButton") is wanted


def test_a_search_by_automation_id_ignores_a_different_one(backend, search):
    window = _element(name="Editor")
    search["roots"] = [window]
    search["under"][id(window)] = [
        _element(name="OK", automation_id="other", cached=True),
    ]
    assert backend._find_raw("OK", None, None, "okButton") is None


def test_a_search_can_match_a_substring(backend, search):
    window = _element(name="Window")
    wanted = _element(name="OK and close", cached=True)
    search["roots"] = [window]
    search["under"][id(window)] = [wanted]
    assert backend._find_raw("ok and", None, None, None,
                             contains=True) is wanted
    assert backend._find_raw("ok and", None, None, None) is None


def test_a_scoped_search_is_allowed_to_go_deeper(backend, search):
    # Naming a window says "it is in here, find it"; not naming one says
    # "look around", and stays cheap. A browser window holds thousands of
    # nodes and a real target can sit well past any small cap.
    window = _element(name="Editor")
    search["roots"] = [window]
    backend._find_raw("nothing", None, None, None)
    unscoped = search["budgets"][0]
    search["budgets"].clear()
    backend._find_raw("nothing", None, None, None, window_title="Editor")
    assert search["budgets"][0] > unscoped


def test_a_search_that_fails_on_the_provider_answers_none(backend, search):
    search["roots"] = [_element(name="Editor")]
    search["walk_error"] = OSError("provider stopped responding")
    assert backend._find_raw("OK", None, None, None) is None


def test_a_search_of_an_empty_desktop_answers_none(backend, search):
    assert backend._find_raw("OK", None, None, None) is None


def test_a_search_gives_up_rather_than_walking_the_whole_desktop(backend,
                                                                 search):
    # Unbounded, a target that is not there walks every window on the
    # desktop and costs about a minute to answer "no".
    first, second = _element(name="one"), _element(name="two")
    search["roots"] = [first, second]
    search["under"][id(first)] = [
        _element(name=f"c{index}", cached=True)
        for index in range(backend_module._FIND_SCAN_LIMIT + 1)
    ]
    assert backend._find_raw("nothing", None, None, None) is None
    assert len(search["budgets"]) == 1, "the second window was never walked"


def test_an_element_that_cannot_be_converted_never_matches(backend):
    broken = RawElement(cached=True)
    del broken.CachedName
    assert backend._raw_matches(broken, {"name": "OK"}, cached=True) is False


# --- converting an element ----------------------------------------------------

def test_an_element_carries_its_name_role_and_geometry():
    raw = _element(name="OK", control_type=50000,
                   rect=Rect(10, 20, 110, 70), process_id=7,
                   automation_id="okButton")
    element = _convert_uia(raw)
    assert element.name == "OK"
    assert element.role == "ControlType_50000"
    assert element.bounds == (10, 20, 100, 50)
    assert element.native_id == "okButton"
    assert element.process_id == 7


def test_a_role_is_reported_as_the_raw_control_type():
    # Translation to a friendly name is a separate step on purpose; the
    # element carries what UIA said.
    assert _convert_uia(_element(control_type=50004)).role == "ControlType_50004"


def test_the_owning_application_is_named_from_its_pid():
    assert _convert_uia(_element(process_id=7)).app_name == "app7.exe"


def test_a_rectangle_that_is_inside_out_reads_as_no_size():
    # An offscreen or collapsed control reports right < left; a negative
    # width would put the element's centre outside the screen.
    element = _convert_uia(_element(rect=Rect(100, 100, 10, 10)))
    assert element.bounds == (100, 100, 0, 0)


def test_a_disabled_control_is_carried_as_disabled():
    assert _convert_uia(_element(enabled=False)).enabled is False


def test_a_cached_element_is_read_from_its_cached_properties():
    # The whole cost of a desktop listing is `Current*` reads, one
    # cross-process call each; cached elements carry them already.
    raw = _element(name="OK", cached=True)
    assert _convert_uia(raw, cached=True).name == "OK"
    assert _convert_uia(raw, cached=False) is None, "no Current* on it"


def test_an_element_that_went_away_mid_conversion_is_none():
    raw = _element(name="OK")
    del raw.CurrentName
    assert _convert_uia(raw) is None


def test_an_element_with_no_name_converts_with_an_empty_one():
    raw = RawElement(name=None, control_type=None, rect=Rect(),
                     process_id=None, automation_id=None, enabled=False)
    element = _convert_uia(raw)
    assert (element.name, element.role) == ("", "ControlType_0")


def test_a_name_read_that_fails_reads_as_empty():
    raw = _element(name="OK")
    del raw.CurrentName
    assert _safe_name(raw) == ""


def test_a_name_is_read_from_the_current_property():
    assert _safe_name(_element(name="OK")) == "OK"


# --- the rich property read ---------------------------------------------------

def test_the_rich_properties_are_read_one_by_one():
    raw = types.SimpleNamespace(
        CurrentIsEnabled=True, CurrentIsOffscreen=False,
        CurrentHelpText="press me", CurrentItemStatus="busy",
        CurrentAcceleratorKey="Ctrl+S", CurrentAccessKey="s",
        CurrentOrientation=1,
    )
    assert _read_properties(raw) == {
        "enabled": True, "offscreen": False, "help_text": "press me",
        "item_status": "busy", "accelerator_key": "Ctrl+S",
        "access_key": "s", "orientation": 1,
    }


def test_a_property_the_provider_will_not_answer_reads_as_none():
    # Each key is present either way: a missing key and a null value are
    # different answers to the caller.
    assert _read_properties(types.SimpleNamespace()) == {
        "enabled": None, "offscreen": None, "help_text": None,
        "item_status": None, "accelerator_key": None, "access_key": None,
        "orientation": None,
    }


def test_a_property_of_the_wrong_type_reads_as_none():
    raw = types.SimpleNamespace(CurrentOrientation="sideways")
    assert _read_properties(raw)["orientation"] is None


def test_get_properties_needs_a_control_to_read_them_from(backend, listing):
    assert backend.get_properties(name="OK") is None


def test_get_properties_reads_the_control_it_found(backend, listing):
    window = _element(name="Editor")
    window.CurrentHelpText = "the editor"
    listing["roots"] = [window]
    assert backend.get_properties(name="Editor")["help_text"] == "the editor"


# --- naming a process ---------------------------------------------------------

@pytest.mark.parametrize("pid", [0, -1])
def test_a_process_id_that_is_not_one_has_no_name(pid):
    assert _process_name(pid) == ""


@pytest.mark.skipif(sys.platform == "win32",
                    reason="on Windows the real lookup runs")
def test_off_windows_no_process_lookup_is_attempted():
    assert _process_name(4321) == ""


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 API")
def test_this_interpreters_own_process_names_itself():
    import os
    assert _process_name(os.getpid()).lower().startswith("python")


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 API")
def test_a_process_that_is_not_there_has_no_name():
    # OpenProcess fails and the name is empty rather than an exception out of
    # the middle of a desktop listing.
    assert _process_name(0x7FFFFFFF) == ""


def test_the_process_name_lookup_is_cached():
    # A desktop listing asks about the same handful of pids thousands of
    # times, and each miss is three Win32 round trips.
    assert hasattr(_process_name, "cache_info")
    before = _process_name.cache_info()
    _process_name(0)
    _process_name(0)
    after = _process_name.cache_info()
    assert after.hits > before.hits
