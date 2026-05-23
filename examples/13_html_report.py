"""Run a few actions with recording enabled, then emit an HTML report.

The test recorder is opt-in: set ``test_record_instance.init_record =
True`` before running anything, and every ``AC_*`` call appends a row
to the in-memory list. ``generate_html_report`` then formats it as a
styled HTML file.
"""
import je_auto_control as ac


def main() -> None:
    # Enable the recorder; without this the report comes out empty.
    ac.test_record_instance.init_record = True

    try:
        ac.get_mouse_position()
        ac.screen_size()
    except Exception as exc:  # noqa: BLE001 — show but don't abort
        print(f"warning: {exc}")

    # Output goes to ``<html_name>.html`` in the current working dir.
    ac.generate_html_report("autocontrol_demo_report")
    print(f"wrote autocontrol_demo_report.html "
          f"with {len(ac.test_record_instance.test_record_list)} rows")

    # If you want the HTML string instead of a file (e.g. to email it
    # or render inside a Qt widget), use generate_html() directly.
    body = ac.generate_html()
    print(f"in-memory report length: {len(body)} chars")


if __name__ == "__main__":
    main()
