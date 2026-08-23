"""A UIAutomation stand-in, so the Windows accessibility backend is testable.

`backends/windows_backend.py` is the largest single gap in the project's
coverage -- 568 statements at 17% -- and it stayed there on the Windows
squares too, because reaching it needs a UIAutomation provider, a desktop
with windows on it, and applications willing to answer. None of that exists
on a CI runner of any platform.

It does not need any of it. Every `comtypes` import in the module is inside a
function, the automation object is held on the instance, and each control
pattern is reached the same way: find a raw element, ask it for a pattern id,
query an interface off the generated module. All three are values a test can
supply.

The shape modelled here is that indirection, because it is where a mistake
hides:

    unknown = raw.GetCurrentPattern(pattern_id)     # None if unsupported
    interface = getattr(uia_module, interface_name)  # generated at import
    pattern = unknown.QueryInterface(interface)

A control that does not support a pattern answers with nothing, and every
caller has to turn that into its own "no" -- `None`, `False`, or `[]`
depending on what it promised to return. `Unknown` below therefore refuses to
hand back a pattern for the wrong interface name, so a method that asks for
`IUIAutomationValuePattern` where it meant `IUIAutomationRangeValuePattern`
fails here rather than silently working against a double that answers
everything.

Nothing here is a test; the file is named so pytest does not collect it.
"""
from __future__ import annotations

import sys
import types


class Rect:
    """What UIA's BoundingRectangle property hands back."""

    def __init__(self, left=0, top=0, right=0, bottom=0) -> None:
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class Pattern:
    """One control pattern: attributes to read, and calls to record."""

    def __init__(self, **attributes) -> None:
        self.__dict__.update(attributes)
        self.calls = []
        self.errors = {}        # method name -> exception to raise

    def _record(self, name, *args):
        self.calls.append((name, args))
        if name in self.errors:
            raise self.errors[name]
        return None

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        # A UIA *property* is spelled `Current…` / `Cached…`; one that was
        # not supplied is one the provider will not answer, which reaches the
        # backend as AttributeError and is a path it handles. Answering with
        # a callable instead would let `str(pattern.CurrentValue or "")` pass
        # against the repr of a function.
        if name.startswith(("Current", "Cached")):
            raise AttributeError(name)

        def _call(*args):
            return self._record(name, *args)
        return _call


class Unknown:
    """What `GetCurrentPattern` returns: an IUnknown to query an interface off."""

    def __init__(self, interface_name: str, pattern: Pattern) -> None:
        self.interface_name = interface_name
        self.pattern = pattern
        self.queried = []

    def QueryInterface(self, interface):    # noqa: N802  # reason: COM name
        self.queried.append(interface)
        if interface != self.interface_name:
            raise TypeError(
                f"asked for {interface!r}, this pattern is "
                f"{self.interface_name!r}")
        return self.pattern


class RawElement:
    """A raw UIA element: properties, patterns, and what was done to it."""

    def __init__(self, name="", control_type=0, rect=None, process_id=0,
                 automation_id="", enabled=True, patterns=None,
                 properties=None, cached=False) -> None:
        self.patterns = dict(patterns or {})     # pattern id -> Unknown
        self.properties = dict(properties or {})  # property id -> value
        self.focused = 0
        self.pattern_error = None
        self.property_error = None
        self.focus_error = None
        prefix = "Cached" if cached else "Current"
        setattr(self, prefix + "Name", name)
        setattr(self, prefix + "ControlType", control_type)
        setattr(self, prefix + "BoundingRectangle", rect or Rect())
        setattr(self, prefix + "ProcessId", process_id)
        setattr(self, prefix + "AutomationId", automation_id)
        setattr(self, prefix + "IsEnabled", enabled)
        # `_convert_uia` reads one prefix or the other; a raw element that
        # only ever appears cached must not answer to `Current*`.
        self._prefix = prefix

    def GetCurrentPattern(self, pattern_id):    # noqa: N802  # reason: UIA name
        if self.pattern_error is not None:
            raise self.pattern_error
        return self.patterns.get(pattern_id)

    def GetCurrentPropertyValue(self, property_id):  # noqa: N802  # UIA name
        if self.property_error is not None:
            raise self.property_error
        return self.properties.get(property_id)

    def SetFocus(self):     # noqa: N802  # reason: the UIA name
        if self.focus_error is not None:
            raise self.focus_error
        self.focused += 1


class ElementArray:
    """An `IUIAutomationElementArray`: a length and indexed access."""

    def __init__(self, elements=None, length_error=None,
                 element_error=None) -> None:
        self.elements = list(elements or [])
        self.length_error = length_error
        self.element_error = element_error

    @property
    def Length(self):       # noqa: N802  # reason: the UIA name
        if self.length_error is not None:
            raise self.length_error
        return len(self.elements)

    def GetElement(self, index):    # noqa: N802  # reason: the UIA name
        if self.element_error is not None:
            raise self.element_error
        return self.elements[index]


class UiaModule:
    """The comtypes-generated `UIAutomationClient` module.

    Its interfaces are generated at import time, so a name is all there is to
    hold on to; `getattr` therefore answers with the name itself and
    `Unknown` compares against it.
    """

    def __init__(self, has_iuiautomation2: bool = True) -> None:
        self._has_2 = has_iuiautomation2
        self.IUIAutomation = "IUIAutomation"

    def __getattr__(self, name):
        # An older Windows generates a module without IUIAutomation2 at all,
        # which is the fallback the backend is written to take -- so the
        # absence has to be a real AttributeError, not a name that answers.
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "IUIAutomation2" and not self._has_2:
            raise AttributeError(name)
        return name


class Automation:
    """The UIAutomation object: roots, a walker, and event handler bookkeeping."""

    def __init__(self, root=None) -> None:
        self.root = root
        self.focus_handlers = []
        self.add_error = None
        self.remove_error = None
        self.ConnectionTimeout = None   # noqa: N815  # reason: the UIA name

    def GetRootElement(self):       # noqa: N802  # reason: the UIA name
        return self.root

    def AddFocusChangedEventHandler(self, cache_request, handler):  # noqa: N802
        if self.add_error is not None:
            raise self.add_error
        self.focus_handlers.append(handler)

    def RemoveFocusChangedEventHandler(self, handler):  # noqa: N802
        if self.remove_error is not None:
            raise self.remove_error
        if handler in self.focus_handlers:
            self.focus_handlers.remove(handler)


def with_pattern(pattern_id: int, interface_name: str,
                 pattern: Pattern = None) -> dict:
    """A `patterns` mapping carrying one pattern, ready for `RawElement`."""
    return {pattern_id: Unknown(interface_name, pattern or Pattern())}


def install_comtypes(monkeypatch, uia_module=None, module_error=None,
                     create=None):
    """Put a `comtypes` package in `sys.modules` and return what it hands out.

    Only the four names the backend reaches for: `client.GetModule`, which
    generates the UIAutomationClient module, and `CoCreateInstance` / `GUID` /
    `COMObject`, which build the automation object and the event handler.
    """
    created = []

    def _co_create_instance(clsid, interface=None):
        created.append((clsid, interface))
        if create is not None:
            return create(clsid, interface)
        return Automation()

    comtypes = types.ModuleType("comtypes")
    comtypes.CoCreateInstance = _co_create_instance
    comtypes.GUID = lambda text: text

    class _ComObject:
        """The base comtypes gives a Python-implemented COM interface."""

    comtypes.COMObject = _ComObject

    client = types.ModuleType("comtypes.client")

    def _get_module(name):
        if module_error is not None:
            raise module_error
        return uia_module if uia_module is not None else UiaModule()

    client.GetModule = _get_module
    comtypes.client = client

    monkeypatch.setitem(sys.modules, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", client)
    return created
