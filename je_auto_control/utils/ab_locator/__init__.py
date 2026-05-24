"""A/B locator framework — race N strategies, record per-strategy wins.

Public surface::

    from je_auto_control import (
        ABRunOutcome, ab_locate, ab_best_strategy, ab_report_for,
    )
    from je_auto_control.utils.anchor_locator import (
        image_locator, ocr_locator, vlm_locator,
    )

    outcome = ab_locate(
        target_id="submit_button",
        strategies={
            "image": image_locator("submit.png"),
            "ocr": ocr_locator("Submit"),
            "vlm": vlm_locator("the green Submit button"),
        },
    )
    print("winner:", outcome.winner)
    print("historical best:", ab_best_strategy("submit_button"))
"""
from je_auto_control.utils.ab_locator.runner import (
    ABRunOutcome, StrategyResult, ab_locate,
    best_strategy as ab_best_strategy,
    report_for as ab_report_for,
)
from je_auto_control.utils.ab_locator.store import (
    ABReport, ABStore, ABStrategyStats, default_ab_store,
)


__all__ = [
    "ABReport", "ABRunOutcome", "ABStore", "ABStrategyStats",
    "StrategyResult", "ab_best_strategy", "ab_locate",
    "ab_report_for", "default_ab_store",
]
