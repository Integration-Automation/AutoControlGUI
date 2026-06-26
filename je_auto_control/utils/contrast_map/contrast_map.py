"""Grade the legibility of on-screen text by sampling its actual colours.

:func:`a11y_audit.contrast_ratio` grades a foreground / background pair you
already know. But when you only have a *region* of the screen — a button, a
label — you don't know those two colours; you have a patch of pixels.
``contrast_map`` closes that gap: split a sampled region into its dominant
foreground (the minority — usually the text) and background (the majority)
colours, then grade their WCAG contrast.

* :func:`grade_contrast` — pure: a foreground / background pair to
  ``{ratio, aa, aaa, aa_large, aaa_large}`` against the WCAG 2.x thresholds.
* :func:`dominant_pair` — pure: split a list of sampled RGB pixels into the
  dominant ``{foreground, background}`` colours by luminance.
* :func:`region_contrast` — sample a screen region and grade it, through an
  injectable ``sampler`` (the real screen grab by default).

The grading and split are pure and reuse :func:`a11y_audit.contrast_ratio`, so
they are fully testable without a screen. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence

from je_auto_control.utils.a11y_audit import contrast_ratio
from je_auto_control.utils.a11y_audit.audit import relative_luminance

# WCAG 2.x contrast thresholds.
_AA_NORMAL = 4.5
_AAA_NORMAL = 7.0
_AA_LARGE = 3.0
_AAA_LARGE = 4.5

RGB = List[int]
PixelSampler = Callable[[Optional[Sequence[int]]], List[Sequence[int]]]


def grade_contrast(foreground: Sequence[float],
                   background: Sequence[float]) -> Dict[str, Any]:
    """Grade a foreground / background colour pair against WCAG (pure).

    Returns ``{ratio, aa, aaa, aa_large, aaa_large}`` — the contrast ratio and
    whether it meets AA / AAA for normal and large text.
    """
    ratio = contrast_ratio(foreground, background)
    return {
        "ratio": round(ratio, 3),
        "aa": ratio >= _AA_NORMAL,
        "aaa": ratio >= _AAA_NORMAL,
        "aa_large": ratio >= _AA_LARGE,
        "aaa_large": ratio >= _AAA_LARGE,
    }


def _mean_color(pixels: Sequence[Sequence[int]]) -> RGB:
    """Average a non-empty list of RGB pixels to one colour (pure)."""
    count = len(pixels)
    totals = [0, 0, 0]
    for pixel in pixels:
        totals[0] += int(pixel[0])
        totals[1] += int(pixel[1])
        totals[2] += int(pixel[2])
    return [totals[0] // count, totals[1] // count, totals[2] // count]


def _partition_by_luminance(rgbs: Sequence[Sequence[int]]) -> tuple:
    """Split RGB pixels into (darker, lighter) groups at the mean luminance."""
    lums = [relative_luminance(rgb) for rgb in rgbs]
    average = sum(lums) / len(lums)
    low = [rgb for rgb, lum in zip(rgbs, lums) if lum < average]
    high = [rgb for rgb, lum in zip(rgbs, lums) if lum >= average]
    return low, high


def dominant_pair(pixels: Sequence[Sequence[int]]) -> Dict[str, RGB]:
    """Split sampled pixels into dominant foreground / background colours (pure).

    Pixels are partitioned at the mean luminance; the larger group is the
    background and the smaller the foreground (text). A uniform region yields
    the same colour for both (no contrast). Returns ``{foreground, background}``.
    """
    rgbs = [(int(p[0]), int(p[1]), int(p[2])) for p in pixels]
    if not rgbs:
        return {"foreground": [0, 0, 0], "background": [0, 0, 0]}
    low, high = _partition_by_luminance(rgbs)
    if not low or not high:
        mean = _mean_color(rgbs)
        return {"foreground": mean, "background": mean}
    background, foreground = (high, low) if len(high) >= len(low) else (low,
                                                                        high)
    return {"foreground": _mean_color(foreground),
            "background": _mean_color(background)}


def _default_sampler(region: Optional[Sequence[int]]) -> List[RGB]:
    """Grab a screen region and return a capped list of its RGB pixels."""
    from je_auto_control.utils.color_region.color_region import _grab_rgb
    array = _grab_rgb(region)
    flat = array.reshape(-1, array.shape[-1])
    step = max(1, len(flat) // 4096)
    return [[int(px[0]), int(px[1]), int(px[2])] for px in flat[::step]]


def region_contrast(*, sampler: Optional[PixelSampler] = None,
                    region: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """Sample a screen ``region`` and grade its text contrast.

    Pass ``sampler`` (``region -> list of RGB pixels``) to supply pixels in
    tests; the default grabs the real screen. Returns the
    :func:`grade_contrast` result plus ``{foreground, background, samples}``.
    """
    sample = sampler if sampler is not None else _default_sampler
    pixels = list(sample(region))
    pair = dominant_pair(pixels)
    grade = grade_contrast(pair["foreground"], pair["background"])
    return {**grade, "foreground": pair["foreground"],
            "background": pair["background"], "samples": len(pixels)}
