"""macOS accessibility backend via pyobjc's ``ApplicationServices``.

Requires Accessibility permission for the Python interpreter (System
Settings → Privacy & Security → Accessibility). Enumerates the frontmost
application's window tree, or a specific ``app_name``.
"""
from typing import List, Optional

from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def _is_available() -> bool:
    try:
        import ApplicationServices  # noqa: F401  # reason: probe import
        import AppKit  # noqa: F401  # reason: probe import
        return True
    except ImportError:
        return False


class MacOSAccessibilityBackend(AccessibilityBackend):
    """Accessibility walker using ``AXUIElement*`` APIs."""

    name = "macos-ax"

    def __init__(self) -> None:
        self.available = _is_available()

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      ) -> List[AccessibilityElement]:
        if not self.available:
            raise AccessibilityNotAvailableError(
                "pyobjc (ApplicationServices, AppKit) is required for "
                "macOS accessibility",
            )
        import ApplicationServices as ax_module
        import AppKit

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        running_apps = list(workspace.runningApplications())
        results: List[AccessibilityElement] = []
        for app in running_apps:
            if not app.isActive() and app_name is None:
                continue
            name = str(app.localizedName() or "")
            if app_name is not None and name != app_name:
                continue
            pid = int(app.processIdentifier())
            try:
                root = ax_module.AXUIElementCreateApplication(pid)
                self._walk(ax_module, root, name, pid, results, max_results)
            except Exception as error:  # noqa: BLE001  # reason: AX errors vary
                autocontrol_logger.warning(
                    "AX walk failed for %s (%d): %r", name, pid, error,
                )
            if len(results) >= max_results:
                break
        return results[:max_results]

    def _walk(self, ax_module, element, app_name: str, pid: int,
              results: List[AccessibilityElement], max_results: int) -> None:
        if len(results) >= max_results:
            return
        converted = _convert_ax(ax_module, element, app_name, pid)
        if converted is not None:
            results.append(converted)
        err, children = ax_module.AXUIElementCopyAttributeValue(
            element, "AXChildren", None,
        )
        if err or children is None:
            return
        for child in children:
            if len(results) >= max_results:
                return
            self._walk(ax_module, child, app_name, pid, results, max_results)


def _convert_ax(ax_module, element, app_name: str, pid: int,
                ) -> Optional[AccessibilityElement]:
    try:
        _err, role = ax_module.AXUIElementCopyAttributeValue(
            element, "AXRole", None,
        )
        _err, title = ax_module.AXUIElementCopyAttributeValue(
            element, "AXTitle", None,
        )
        _err, position = ax_module.AXUIElementCopyAttributeValue(
            element, "AXPosition", None,
        )
        _err, size = ax_module.AXUIElementCopyAttributeValue(
            element, "AXSize", None,
        )
    except Exception:  # noqa: BLE001  # reason: AX errors vary
        return None
    if role is None and title is None:
        return None
    bounds = _extract_bounds(position, size)
    return AccessibilityElement(
        name=str(title or ""),
        role=str(role or ""),
        bounds=bounds, app_name=app_name, process_id=pid,
    )


def _extract_bounds(position, size) -> tuple:
    try:
        if position is None or size is None:
            return (0, 0, 0, 0)
        x, y = position
        w, h = size
        return (int(x), int(y), int(w), int(h))
    except (TypeError, ValueError):
        return (0, 0, 0, 0)
