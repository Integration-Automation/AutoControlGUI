"""Where to start a UIA search, and how to fetch its properties in bulk.

Two things decide what a desktop-wide accessibility search costs:

* **The root.** ``TreeScope_Descendants`` from the desktop walks every top-level
  window's whole subtree, cross-process. Measured on a busy desktop: 2,085
  elements in 61 s, against 135 elements in 0.14 s starting from one window. So
  scoping to a window is not a filter applied afterwards — it is a different
  search.
* **The properties.** Every ``Current*`` read is another cross-process call, so
  reading five properties from a few thousand elements is thousands of round
  trips. The walk asks for them with a cache request, after which reading them
  is free (measured: 500 elements converted in 0.02 s).
* **The provider.** UIA waits on the *application* to answer. A full-screen game
  that never does made one ``ElementFromHandle`` block for 60 s; bounding
  ``IUIAutomation2.ConnectionTimeout`` brings the same call to 1.0 s.

Imports no ``PySide6``.
"""
import sys
from typing import Any, Iterator, List, Optional, Tuple, Type

from je_auto_control.utils.accessibility.element import (
    AccessibilityNotAvailableError,
)

TREE_SCOPE_DESCENDANTS = 4


def _uia_errors() -> Tuple[Type[BaseException], ...]:
    """Exception types a UIA call can raise.

    ``comtypes`` reports provider failures as ``COMError``, which inherits from
    ``Exception`` and from none of the usual suspects — so an ``except
    (OSError, AttributeError)`` around a UIA call does not actually contain it.
    A window that closes mid-walk, or an application that stops responding,
    surfaces exactly that way.
    """
    errors: List[Type[BaseException]] = [OSError, AttributeError, ValueError]
    if sys.platform == "win32":
        from _ctypes import COMError
        errors.append(COMError)
    return tuple(errors)


UIA_ERRORS = _uia_errors()

UIA_NAME_PROPERTY = 30005
UIA_AUTOMATIONID_PROPERTY = 30011
UIA_BOUNDINGRECTANGLE_PROPERTY = 30001
UIA_PROCESSID_PROPERTY = 30002
UIA_CONTROLTYPE_PROPERTY = 30003
UIA_IS_ENABLED_PROPERTY = 30010

# Everything the element conversion reads, fetched in one bulk call.
CACHED_PROPERTIES = (
    UIA_NAME_PROPERTY, UIA_CONTROLTYPE_PROPERTY,
    UIA_BOUNDINGRECTANGLE_PROPERTY, UIA_PROCESSID_PROPERTY,
    UIA_AUTOMATIONID_PROPERTY, UIA_IS_ENABLED_PROPERTY,
)


def search_root(automation, window_title: Optional[str]):
    """The element to search from: one window by title substring, else the desktop."""
    if not window_title:
        return automation.GetRootElement()
    from je_auto_control.windows.window.windows_window_manage import (
        get_all_window_hwnd,
    )
    needle = window_title.strip().lower()
    for hwnd, title in get_all_window_hwnd():
        if needle in (title or "").lower():
            element = automation.ElementFromHandle(hwnd)
            if element is not None:
                return element
    raise AccessibilityNotAvailableError(
        f"no visible window title contains {window_title!r}")


def search_roots(automation, window_title: Optional[str]) -> Iterator[Any]:
    """The roots to search, one at a time, front-most window first.

    Unscoped, this yields each visible top-level window rather than the desktop
    root — same coverage, but the caller can stop once it has enough. That is
    the whole difference between usable and not: reaching the default 200
    elements costs 0.22 s this way, against 61 s for the single desktop walk,
    which cannot be interrupted once started. ``EnumWindows`` returns z-order,
    so the window the user is actually looking at is searched first.
    """
    if window_title:
        yield search_root(automation, window_title)
        return
    from je_auto_control.windows.window.windows_window_manage import (
        get_all_window_hwnd,
    )
    for hwnd, _title in get_all_window_hwnd():
        try:
            element = automation.ElementFromHandle(hwnd)
        except UIA_ERRORS:
            continue                     # window closed between enumerate and use
        if not _is_null(element):
            yield element


def cache_request(automation):
    """A cache request for every property the element conversion reads."""
    request = automation.CreateCacheRequest()
    for prop in CACHED_PROPERTIES:
        request.AddProperty(prop)
    return request


def _is_null(element) -> bool:
    """Whether a walker returned "no such element".

    ``comtypes`` hands back a **wrapper around a NULL pointer**, not ``None``,
    so ``child is not None`` is true at the end of a sibling list and the caller
    collects a phantom element that raises ``ValueError: NULL COM pointer
    access`` the moment anything reads it. Truthiness is the check that works.
    """
    return element is None or not bool(element)


def _children(walker, node, request, limit: int) -> list:
    """Up to ``limit`` control-view children of ``node``, properties cached.

    Capped because the caller can never need more siblings from one node than
    its whole remaining budget — and a node with tens of thousands of children
    would otherwise cost that many calls before the walk could descend.
    """
    out: list = []
    if limit <= 0:
        return out
    try:
        child = walker.GetFirstChildElementBuildCache(node, request)
    except UIA_ERRORS:
        return out
    while not _is_null(child) and len(out) < limit:
        out.append(child)
        try:
            child = walker.GetNextSiblingElementBuildCache(child, request)
        except UIA_ERRORS:
            break
    return out


def walk_elements(automation, root, limit: int) -> Iterator[Any]:
    """Yield up to ``limit`` control elements under ``root``, in reading order.

    The point is that it can be **stopped**. ``FindAll`` is one call that
    returns after walking everything; this walks node by node, so asking for 200
    elements costs 200 elements' worth of work no matter how large the window is
    (measured on this host: 0.036 s for 50, 0.114 s for 200, 0.486 s for 1,000,
    against 10.3 s for one atomic 34,507-element walk).

    Properties come back cached, so the caller reads ``Cached*``.
    """
    request = cache_request(automation)
    walker = automation.ControlViewWalker
    remaining = max(0, int(limit))
    # Depth-first, pre-order: children pushed reversed so they pop left to right.
    stack = list(reversed(_children(walker, root, request, remaining)))
    while stack and remaining > 0:
        node = stack.pop()
        yield node
        remaining -= 1
        if remaining <= 0:
            return
        stack.extend(reversed(_children(walker, node, request, remaining)))
