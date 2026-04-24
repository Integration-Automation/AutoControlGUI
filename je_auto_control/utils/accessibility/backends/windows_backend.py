"""Windows UIAutomation backend via ``comtypes``.

Requires ``pip install comtypes``. If the module is absent, ``available`` is
``False`` and the facade falls back to the Null backend.

Flattens the UIAutomation tree into ``AccessibilityElement`` records one
level at a time starting from the root desktop, filtered by app if needed.
Only ``is_control_element=True`` nodes are surfaced to avoid millions of
decorative text children.
"""
from typing import List, Optional

from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_TREE_SCOPE_DESCENDANTS = 4
_UIA_IS_CONTROL_ELEMENT_PROPERTY = 30016
_UIA_NAME_PROPERTY = 30005


def _is_available() -> bool:
    try:
        import comtypes.client  # noqa: F401  # reason: probe import
        return True
    except ImportError:
        return False


class WindowsAccessibilityBackend(AccessibilityBackend):
    """UIAutomation-based flat element listing."""

    name = "windows-uia"

    def __init__(self) -> None:
        self.available = _is_available()
        self._automation = None

    def _ensure_automation(self):
        if self._automation is not None:
            return self._automation
        if not self.available:
            raise AccessibilityNotAvailableError(
                "comtypes is required for Windows accessibility; "
                "install it with: pip install comtypes",
            )
        import comtypes.client  # noqa: F401
        from comtypes import CoCreateInstance, GUID
        try:
            uia_module = comtypes.client.GetModule("UIAutomationCore.dll")
        except OSError as error:
            raise AccessibilityNotAvailableError(
                f"UIAutomationCore.dll unavailable: {error!r}",
            ) from error
        automation = CoCreateInstance(
            GUID("{ff48dba4-60ef-4201-aa87-54103eef594e}"),
            interface=uia_module.IUIAutomation,
        )
        self._automation = automation
        return automation

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      ) -> List[AccessibilityElement]:
        automation = self._ensure_automation()
        try:
            root = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(
                _UIA_IS_CONTROL_ELEMENT_PROPERTY, True,
            )
            found = root.FindAll(_TREE_SCOPE_DESCENDANTS, condition)
        except (OSError, AttributeError) as error:
            autocontrol_logger.error("UIA FindAll failed: %r", error)
            return []
        results: List[AccessibilityElement] = []
        count = min(max(0, int(max_results)), int(found.Length or 0))
        for idx in range(count):
            element = _convert_uia(found.GetElement(idx))
            if element is None:
                continue
            if app_name is not None and element.app_name != app_name:
                continue
            results.append(element)
        return results


def _convert_uia(raw) -> Optional[AccessibilityElement]:
    try:
        name = str(raw.CurrentName or "")
        control_type = int(raw.CurrentControlType or 0)
        rect = raw.CurrentBoundingRectangle
        process_id = int(raw.CurrentProcessId or 0)
        automation_id = str(raw.CurrentAutomationId or "")
    except (OSError, AttributeError):
        return None
    width = max(0, int(rect.right - rect.left))
    height = max(0, int(rect.bottom - rect.top))
    return AccessibilityElement(
        name=name, role=f"ControlType_{control_type}",
        bounds=(int(rect.left), int(rect.top), width, height),
        app_name=_process_name(process_id),
        process_id=process_id,
        native_id=automation_id,
    )


def _process_name(process_id: int) -> str:
    if process_id <= 0:
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query_information = 0x0400 | 0x0010
        handle = kernel32.OpenProcess(process_query_information, False, process_id)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            get_image = kernel32.QueryFullProcessImageNameW
            if not get_image(handle, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
    except OSError:
        return ""
