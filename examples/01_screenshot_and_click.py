"""Screenshot the desktop, locate a known UI image, then click it.

Requires:
    pip install -e .

The template path below points at an image you saved earlier from the
screen (for example, a button you want to click). Swap it for your own
file before running.
"""
from pathlib import Path

import je_auto_control as ac


def main() -> None:
    template = Path("button.png")
    if not template.exists():
        snapshot = ac.pil_screenshot()
        snapshot.save("screenshot.png")
        print(
            f"saved {Path('screenshot.png').resolve()} — crop the button you "
            f"want to click and save it as {template.resolve()}",
        )
        return

    # locate_and_click takes the template path + a mouse keycode and
    # dispatches a click on the best match's centre. detect_threshold is
    # the OpenCV template-match score — values closer to 1.0 mean stricter
    # matching.
    center = ac.locate_and_click(
        str(template),
        mouse_keycode="mouse_left",
        detect_threshold=0.85,
    )
    print(f"clicked centre at {center}")


if __name__ == "__main__":
    main()
