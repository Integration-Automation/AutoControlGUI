"""Host-owned press announcements and acknowledged releases survive helper termination."""
from __future__ import annotations

import json
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached

_RELEASES = frozenset({"key_release", "key_released", "mouse_release", "mouse_released"})


def _key(event: dict) -> str:
    value = event.get("keycode")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise AgentTaskError("native input requires a concrete key code")
    return ("unicode:" if event.get("unicode") else "key:") + json.dumps(value)


class InputLedger:
    """Keep only keys/buttons this owner authorized, never another task's state."""

    def __init__(self) -> None:
        self._keys: dict[str, dict] = {}
        self._buttons: dict[str, dict] = {}

    @property
    def empty(self) -> bool:
        """Whether all announced press attempts have confirmed releases."""
        return not self._keys and not self._buttons

    def snapshot(self) -> dict[str, Any]:
        """Copy only the owned input needed for narrowly scoped cleanup."""
        return detached({"keys": list(self._keys.values()), "buttons": list(self._buttons.values())})

    def consume(self, event: dict, *, cleanup: bool = False) -> None:
        """Check an event before acknowledging it to the helper."""
        kind = event.get("kind")
        if cleanup and kind not in _RELEASES:
            raise AgentTaskError("cleanup cannot authorize new input")
        handlers = {"key_press": self._key_press, "key_release": self._key_release,
                    "key_released": self._key_released, "mouse_press": self._mouse_press,
                    "mouse_release": self._mouse_release, "mouse_released": self._mouse_released,
                    "pointer": self._nonholding, "scroll": self._nonholding, "text": self._nonholding}
        if not isinstance(kind, str) or kind not in handlers:
            raise AgentTaskError("unrecognized native input event")
        handlers[kind](event)

    def _key_press(self, event: dict) -> None:
        key = _key(event)
        if key in self._keys:
            raise AgentTaskError("key is already held by this task")
        shifted = event.get("is_shift", False)
        if not isinstance(shifted, bool):
            raise AgentTaskError("native modifier flag must be boolean")
        self._keys[key] = {"keycode": event["keycode"], "is_shift": shifted}
        if event.get("unicode"):
            self._keys[key]["unicode"] = True

    def _key_release(self, event: dict) -> None:
        if _key(event) not in self._keys:
            raise AgentTaskError("cannot release a key this task does not own")
        if self._keys[_key(event)]["is_shift"] != event.get("is_shift", False):
            raise AgentTaskError("cannot change a held key's modifier ownership")

    def _key_released(self, event: dict) -> None:
        self._key_release(event)
        self._keys.pop(_key(event))

    def _mouse_press(self, event: dict) -> None:
        key = _key(event)
        if key in self._buttons:
            raise AgentTaskError("button is already held by this task")
        if any(isinstance(event.get(name), bool) or not isinstance(event.get(name), int) for name in ("x", "y")):
            raise AgentTaskError("native pointer requires integer coordinates")
        self._buttons[key] = {name: event[name] for name in ("keycode", "x", "y")}

    def _mouse_release(self, event: dict) -> None:
        if _key(event) not in self._buttons:
            raise AgentTaskError("cannot release a button this task does not own")

    def _mouse_released(self, event: dict) -> None:
        self._mouse_release(event)
        self._buttons.pop(_key(event))

    @staticmethod
    def _nonholding(_event: dict) -> None:
        return None
