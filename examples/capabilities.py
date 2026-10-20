"""Inspect live prerequisites and a deterministic XWayland scope example without operating the desktop."""
import json

from je_auto_control.api import BackendContext, probe_capabilities


def main() -> None:
    """Print passive snapshots; no devices, images, portal requests or native libraries are opened."""
    current = probe_capabilities(BackendContext.current())
    xwayland = probe_capabilities(BackendContext(
        'linux', {'WAYLAND_DISPLAY': 'wayland-example', 'DISPLAY': ':example',
                  'JE_AUTOCONTROL_LINUX_DISPLAY_SERVER': 'x11'}, frozenset(),
    ))
    print(json.dumps({'current': current.to_dict(), 'xwayland_example': xwayland.to_dict()}, indent=2))


if __name__ == '__main__':
    main()
