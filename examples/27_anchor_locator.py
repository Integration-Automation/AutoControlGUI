"""Compose locators with spatial relations.

Real UIs rarely have a unique pixel template for every element; the
``Submit`` button looks the same as four other buttons on the page.
The anchor-based locator solves that by saying: *"find Submit that
sits below the Username label"*. Username is the anchor (resolved by
OCR), Submit is the target (resolved by template match), and the
relation removes false positives.

The anchor and target can use different locator backends — pick the
cheapest one that uniquely identifies each part::

    anchor=ocr_locator("Username")             # text label → OCR
    target=image_locator("submit_green.png")   # graphical button → template
    relation="below"

Other relations: ``above``, ``left_of``, ``right_of``, ``near``
(default; ``max_distance_px`` caps how far is "near").
"""
from je_auto_control import (
    anchor_locate, image_locator, ocr_locator, vlm_locator,
)


def main() -> None:
    # 1) OCR anchor + image target — the canonical form-field flow.
    outcome = anchor_locate(
        anchor=ocr_locator("Username"),
        target=image_locator("submit_green.png"),
        relation="below",
    )
    print(f"submit below username: found={outcome.found}"
          f" coords={outcome.target_coords}"
          f" distance={outcome.distance_px}px")

    # 2) Image anchor + OCR target — find the price text near a logo.
    outcome = anchor_locate(
        anchor=image_locator("brand_logo.png"),
        target=ocr_locator("$"),
        relation="right_of",
    )
    print(f"price right of logo: found={outcome.found}"
          f" coords={outcome.target_coords}")

    # 3) VLM anchor + image target — natural-language anchor for the
    # cases where neither template nor OCR uniquely identify the
    # reference point.
    outcome = anchor_locate(
        anchor=vlm_locator("the orange settings cog in the top bar"),
        target=image_locator("export_icon.png"),
        relation="near", max_distance_px=120.0,
    )
    print(f"export near settings: found={outcome.found}"
          f" coords={outcome.target_coords}")


if __name__ == "__main__":
    main()
