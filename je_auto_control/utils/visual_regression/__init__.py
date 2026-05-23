"""Phase 6.3: visual regression testing for desktop GUIs.

``take_golden(path)`` saves the current screen (or a region / window /
caller-supplied PIL image) under a stable file path. ``compare_to_golden``
loads the same path back and compares — returning a structured
:class:`DiffResult` with the per-pixel difference percentage, an
optional diff-overlay image, and any per-region tolerances.

Typical pytest usage::

    from je_auto_control.utils.visual_regression import (
        compare_to_golden, take_golden,
    )

    def test_login_screen_looks_right(qtbot):
        ...  # navigate the GUI
        result = compare_to_golden(
            "tests/goldens/login.png", tolerance=0.5,
        )
        if not result.matched:
            take_golden("tests/goldens/login.actual.png")
            result.write_diff("tests/goldens/login.diff.png")
            pytest.fail(result.summary)

The framework is intentionally PIL-only — no SciPy / OpenCV dependency
— so it ships with the headless test suite. Region masks let you
exclude a clock / animated banner / random session-id area from the
comparison.
"""
from je_auto_control.utils.visual_regression.compare import (
    DiffResult, MaskRegion, compare_to_golden, image_difference,
    take_golden,
)

__all__ = [
    "DiffResult", "MaskRegion",
    "compare_to_golden", "image_difference", "take_golden",
]
