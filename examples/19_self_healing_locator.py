"""Locate a UI element with image-template first, VLM fallback on miss.

Pass ``template_path`` *and* ``description`` so the call survives:

* template hit → use OpenCV match (fast, free, no network);
* template miss → ask the VLM to find the element by description;
* both miss → ``outcome.found`` is False; the caller decides what
  to do (re-screenshot, give up, escalate).

Every attempt is appended to the JSON-lines audit log at
``~/.je_auto_control/self_healing_events.jsonl`` so flaky locators
can be tuned over time.
"""
from je_auto_control import (
    default_heal_log, self_heal_click, self_heal_locate,
)


def main() -> None:
    outcome = self_heal_locate(
        template_path="submit_button.png",
        description="the green Submit button at the bottom right",
        detect_threshold=0.9,
    )
    if outcome.found:
        print(f"Found via {outcome.method} at {outcome.coordinates}"
              f" in {outcome.duration_ms:.1f} ms")
    else:
        print(f"Miss — image_error={outcome.image_error!r}"
              f" vlm_error={outcome.vlm_error!r}")

    # Same call but also clicks when the locator resolves a point.
    self_heal_click(
        template_path="submit_button.png",
        description="the green Submit button at the bottom right",
        mouse_keycode="mouse_left",
    )

    # Inspect the audit log — both attempts are recorded.
    for event in default_heal_log.list_events(limit=5):
        print(f"  {event.timestamp} {event.method} -> {event.coordinates}")


if __name__ == "__main__":
    main()
