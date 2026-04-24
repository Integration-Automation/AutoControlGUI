"""Abstract hotkey backend contract."""
from je_auto_control.utils.hotkey.hotkey_daemon import BackendContext


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
