"""Abstract hotkey backend contract."""
from typing import Dict, Iterable

from je_auto_control.utils.hotkey.hotkey_daemon import BackendContext, HotkeyBinding


class FailedCombos:
    """Bindings whose current combo could not be registered, so it is not retried.

    A backend re-syncs its bindings several times a second; retrying a combo
    that cannot be parsed or grabbed logged an error on every tick for as
    long as the daemon ran. A binding is tried again once its combo changes.
    """

    def __init__(self) -> None:
        self._combos: Dict[str, str] = {}

    def blocked(self, binding: HotkeyBinding) -> bool:
        """Whether ``binding``'s current combo already failed."""
        return self._combos.get(binding.binding_id) == binding.combo

    def record(self, binding: HotkeyBinding) -> None:
        """Remember that ``binding``'s current combo failed."""
        self._combos[binding.binding_id] = binding.combo

    def clear(self, binding_id: str) -> None:
        """Forget a failure once the binding registered."""
        self._combos.pop(binding_id, None)

    def forget_missing(self, current_ids: Iterable[str]) -> None:
        """Drop failures of bindings that no longer exist."""
        keep = set(current_ids)
        for binding_id in [bid for bid in self._combos if bid not in keep]:
            del self._combos[binding_id]


class HotkeyBackend:
    """Each backend owns a thread and listens for OS-level hotkey presses.

    Implementations must:
      * poll ``context.get_bindings()`` so added / removed bindings take
        effect without restarting the daemon;
      * call ``context.fire(binding_id)`` from the listener thread whenever
        a registered hotkey is observed;
      * return as soon as ``context.stop_event`` is set.
    """

    name: str = "abstract"

    def run_forever(self, context: BackendContext) -> None:  # pragma: no cover
        raise NotImplementedError
