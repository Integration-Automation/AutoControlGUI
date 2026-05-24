"""Maintain a presence roster across multiple connected viewers.

The presence registry stores ``viewer_id → ViewerPresence`` rows and
fans changes out via listener callbacks. Plug it into the multi-viewer
remote-desktop host to:

* show every viewer in the host-side roster GUI (Viewer Roster tab);
* gate input dispatch by role — only ``controller`` viewers push
  mouse / keyboard events; ``observer`` viewers are read-only;
* render ghost cursors for the other viewers on each viewer's UI.

This example exercises the headless API only — no aiortc / GUI deps
needed — so you can build the same logic into a CI smoke test.
"""
import je_auto_control as ac


def main() -> None:
    registry = ac.default_presence_registry()
    registry.register("viewer-1", "Alice", role=ac.ROLE_CONTROLLER)
    registry.register("viewer-2", "Bob")
    registry.register("viewer-3", "Carol")

    registry.update_cursor("viewer-2", x=240, y=120)
    registry.update_role("viewer-3", ac.ROLE_CONTROLLER)

    for row in registry.list():
        cursor = (f"@({row.cursor_x},{row.cursor_y})"
                  if row.cursor_x is not None else "")
        marker = "*" if row.role == ac.ROLE_CONTROLLER else " "
        print(f"{marker} {row.viewer_id:<12} {row.label:<10} "
              f"{row.role:<10} {cursor} last_seen={row.last_seen_iso}")

    print(f"\ncontrollers: {registry.controller_ids()}")
    print(f"total connected: {registry.count()}")


if __name__ == "__main__":
    main()
