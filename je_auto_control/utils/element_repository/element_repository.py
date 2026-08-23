"""Named locator repository (the classic RPA *object repository*).

Save native-UI locators under friendly names once, reuse them everywhere
— so flows reference ``"login.submit"`` instead of repeating
``name="Submit", role="button"`` at every call site, and a UI change is
fixed in one place. A locator is a small set of accessibility filters
(``name`` / ``role`` / ``app_name``); resolving it finds the live element
through the accessibility backend.

Pure standard library (JSON file storage); imports no ``PySide6``. The
accessibility backend is imported lazily so storage works on any platform.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_FILTER_FIELDS = ("name", "role", "app_name")


class ElementRepository:
    """A JSON-backed map of friendly name -> accessibility locator."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._items: Dict[str, Dict[str, str]] = self._load()

    def _load(self) -> Dict[str, Dict[str, str]]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{self._path} is not a locator map")
        return {str(k): dict(v) for k, v in data.items()}

    def _flush(self) -> None:
        self._path.write_text(
            json.dumps(self._items, indent=2, ensure_ascii=False),
            encoding="utf-8")

    def save(self, key: str, *, name: Optional[str] = None,
             role: Optional[str] = None,
             app_name: Optional[str] = None) -> Dict[str, str]:
        """Store a locator under ``key``; needs at least one filter."""
        locator = {field: value for field, value in
                   (("name", name), ("role", role), ("app_name", app_name))
                   if value is not None}
        if not locator:
            raise ValueError("a locator needs at least one of name/role/"
                             "app_name")
        self._items[str(key)] = locator
        self._flush()
        return dict(locator)

    def get(self, key: str) -> Optional[Dict[str, str]]:
        """Return the stored locator for ``key`` (a copy) or ``None``."""
        locator = self._items.get(str(key))
        return dict(locator) if locator is not None else None

    def remove(self, key: str) -> bool:
        """Delete a locator; return whether it existed."""
        existed = str(key) in self._items
        if existed:
            del self._items[str(key)]
            self._flush()
        return existed

    def keys(self) -> List[str]:
        """Return the saved locator names, sorted."""
        return sorted(self._items)

    def all(self) -> Dict[str, Dict[str, str]]:
        """Return a copy of the whole repository."""
        return {key: dict(value) for key, value in self._items.items()}

    def _require(self, key: str) -> Dict[str, str]:
        """Return the stored locator for ``key``, rejecting unknown fields.

        A repository file is user-editable, so a field no accessibility
        filter accepts used to surface as a ``TypeError`` about keyword
        arguments from inside the backend call.
        """
        locator = self.get(key)
        if locator is None:
            raise KeyError(f"no locator named {key!r}")
        unknown = sorted(set(locator) - set(_FILTER_FIELDS))
        if unknown:
            raise ValueError(
                f"locator {key!r} has fields that are not accessibility "
                f"filters: {', '.join(unknown)}")
        return locator

    def resolve(self, key: str) -> Any:
        """Find the live element for ``key`` (or ``None`` if not present)."""
        from je_auto_control.utils.accessibility import (
            find_accessibility_element)
        locator = self._require(key)
        return find_accessibility_element(
            name=locator.get("name"), role=locator.get("role"),
            app_name=locator.get("app_name"))

    def find_info(self, key: str) -> Dict[str, Any]:
        """Resolve ``key`` and return a serialisable summary."""
        element = self.resolve(key)
        if element is None:
            return {"found": False}
        return {"found": True, "name": element.name, "role": element.role,
                "center": list(element.center)}

    def click(self, key: str) -> bool:
        """Click the element for ``key``; return whether it matched."""
        from je_auto_control.utils.accessibility import (
            click_accessibility_element)
        locator = self._require(key)
        return click_accessibility_element(
            name=locator.get("name"), role=locator.get("role"),
            app_name=locator.get("app_name"))
