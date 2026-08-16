"""Tests for the cross-platform accessibility API."""
from typing import List, Optional

import pytest

from je_auto_control.utils.accessibility import backends as backends_mod
from je_auto_control.utils.accessibility.accessibility_api import (
    find_accessibility_element, list_accessibility_elements,
)
from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.backends.null_backend import (
    NullAccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError, element_matches,
)


class _FakeBackend(AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, elements: List[AccessibilityElement]) -> None:
        self._elements = elements
        self.last_args: Optional[dict] = None

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      window_title: Optional[str] = None,
                      ) -> List[AccessibilityElement]:
        self.last_args = {"app_name": app_name, "max_results": max_results,
                          "window_title": window_title}
        if app_name is None:
            return list(self._elements)
        return [e for e in self._elements if e.app_name == app_name]


@pytest.fixture
def sample_elements():
    return [
        AccessibilityElement(
            name="OK", role="Button",
            bounds=(10, 20, 80, 30), app_name="Calculator",
        ),
        AccessibilityElement(
            name="Cancel", role="Button",
            bounds=(100, 20, 80, 30), app_name="Calculator",
        ),
        AccessibilityElement(
            name="File", role="MenuItem",
            bounds=(0, 0, 50, 20), app_name="Notepad",
        ),
    ]


@pytest.fixture
def fake_backend(sample_elements):
    backend = _FakeBackend(sample_elements)
    backends_mod._cached_backend = backend
    try:
        yield backend
    finally:
        backends_mod.reset_backend_cache()


def test_center_midpoint_of_bounds():
    element = AccessibilityElement(
        name="btn", role="Button", bounds=(10, 20, 80, 40),
    )
    assert element.center == (50, 40)


def test_to_dict_round_trips_bounds_and_center():
    element = AccessibilityElement(
        name="n", role="r", bounds=(1, 2, 3, 4),
        app_name="A", process_id=9, native_id="abc",
    )
    payload = element.to_dict()
    assert payload["bounds"] == [1, 2, 3, 4]
    assert payload["center"] == [2, 4]
    assert payload["app_name"] == "A"
    assert payload["process_id"] == 9
    assert payload["native_id"] == "abc"


def test_element_matches_name_role_app_combinations():
    element = AccessibilityElement(
        name="OK", role="Button",
        bounds=(0, 0, 10, 10), app_name="Calculator",
    )
    assert element_matches(element, name="OK")
    assert element_matches(element, role="button")  # case-insensitive
    assert element_matches(element, app_name="Calculator")
    assert element_matches(element, name="OK", role="Button",
                           app_name="Calculator")
    assert not element_matches(element, name="Cancel")
    assert not element_matches(element, role="MenuItem")
    assert not element_matches(element, app_name="Notepad")


def test_null_backend_raises_with_custom_reason():
    backend = NullAccessibilityBackend("because reasons")
    assert backend.available is False
    with pytest.raises(AccessibilityNotAvailableError) as info:
        backend.list_elements()
    assert "because reasons" in str(info.value)


def test_reset_backend_cache_clears_cached_instance():
    backends_mod._cached_backend = _FakeBackend([])
    assert backends_mod.get_backend() is backends_mod._cached_backend
    backends_mod.reset_backend_cache()
    assert backends_mod._cached_backend is None


def test_list_elements_passes_filters_through(fake_backend):
    result = list_accessibility_elements(app_name="Calculator",
                                         max_results=50)
    assert fake_backend.last_args == {
        "app_name": "Calculator", "max_results": 50, "window_title": None,
    }
    assert len(result) == 2
    assert all(e.app_name == "Calculator" for e in result)


def test_find_element_returns_first_match(fake_backend):
    element = find_accessibility_element(
        name="File", app_name="Notepad",
    )
    assert element is not None
    assert element.role == "MenuItem"


def test_find_element_returns_none_when_no_match(fake_backend):
    assert find_accessibility_element(
        name="Nope", app_name="Calculator",
    ) is None


# --- substring matching and ranking ----------------------------------------

def test_exact_name_match_is_still_the_default(fake_backend):
    # Callers holding a full name must keep getting exactly that element.
    assert find_accessibility_element(name="OK") is not None
    assert find_accessibility_element(name="O") is None


def test_contains_finds_names_with_accelerators_and_padding():
    # Real labels carry accelerator markers and trailing spaces, so an exact
    # comparison misses a large share of genuine targets.
    padded = AccessibilityElement(name="Save(&S) ", role="Button",
                                  bounds=(0, 0, 10, 10), app_name="Editor")
    assert element_matches(padded, name="save", contains=True)
    assert not element_matches(padded, name="save")


def test_contains_ranks_an_exact_name_first():
    from je_auto_control.utils.accessibility.element import rank_by_name
    elements = [
        AccessibilityElement(name="OK and close", role="Button",
                             bounds=(0, 0, 10, 10)),
        AccessibilityElement(name="OK", role="Button", bounds=(0, 50, 10, 10)),
    ]
    # ...even though the exact one is lower down the screen
    assert [e.name for e in rank_by_name(elements, "OK")] == [
        "OK", "OK and close"]


def test_role_filter_accepts_the_friendly_name():
    # The Windows backend reports the raw UIA role on purpose, but nobody
    # filtering a search types "ControlType_50000" — and a role that never
    # matches reads as "element not found".
    raw = AccessibilityElement(name="OK", role="ControlType_50000",
                               bounds=(0, 0, 10, 10))
    assert element_matches(raw, role="button")
    assert element_matches(raw, role="ControlType_50000")
    assert not element_matches(raw, role="edit")
    # a backend that already reports friendly roles keeps working
    friendly = AccessibilityElement(name="OK", role="Button",
                                    bounds=(0, 0, 10, 10))
    assert element_matches(friendly, role="button")
    assert element_matches(friendly, role="ControlType_50000")


def test_find_all_returns_every_hit_best_first(fake_backend):
    from je_auto_control.utils.accessibility.accessibility_api import (
        find_accessibility_elements,
    )
    found = find_accessibility_elements(name="o", contains=True)
    assert [e.name for e in found] == sorted(
        (e.name for e in found), key=lambda n: n.strip().lower() != "o")


def test_find_caps_matches_and_scan_separately(fake_backend):
    # One number cannot mean both: using the match cap as the scan cap turns
    # "up to 2 buttons" into "only look at the first 2 elements".
    from je_auto_control.utils.accessibility.accessibility_api import (
        find_accessibility_elements,
    )
    found = find_accessibility_elements(name="o", contains=True, max_results=1,
                                        scan_limit=500)
    assert len(found) <= 1
    assert fake_backend.last_args["max_results"] == 500   # the scan, not the cap


def test_window_title_is_forwarded_to_the_backend(fake_backend):
    list_accessibility_elements(window_title="Untitled - Notepad")
    assert fake_backend.last_args["window_title"] == "Untitled - Notepad"


def test_window_title_is_omitted_when_not_requested(fake_backend):
    # Left out entirely so a backend written before scoping existed keeps
    # working for every call that does not ask for it.
    list_accessibility_elements()
    assert fake_backend.last_args["window_title"] is None


def test_executor_registers_a11y_commands():
    from je_auto_control.utils.executor.action_executor import executor
    commands = executor.known_commands()
    assert "AC_a11y_list" in commands
    assert "AC_a11y_find" in commands
    assert "AC_a11y_find_all" in commands
    assert "AC_a11y_click" in commands
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_a11y_find", "ac_a11y_find_all"} <= names


def test_executor_flag_coercion_treats_string_false_as_false():
    # A JSON action file / CLI / MCP call can deliver "false", which is truthy.
    from je_auto_control.utils.executor.action_executor import _as_bool
    assert _as_bool("false") is False and _as_bool("0") is False
    assert _as_bool("true") is True and _as_bool(True) is True


def test_package_facade_exports_accessibility_api():
    import je_auto_control as ac
    assert hasattr(ac, "AccessibilityElement")
    assert hasattr(ac, "AccessibilityNotAvailableError")
    assert hasattr(ac, "list_accessibility_elements")
    assert hasattr(ac, "find_accessibility_element")
    assert hasattr(ac, "click_accessibility_element")
