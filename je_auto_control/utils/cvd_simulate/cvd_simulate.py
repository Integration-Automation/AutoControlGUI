"""Simulate colour-vision deficiency and flag colours that collide under it.

Status UIs lean on colour — a green "ok" vs a red "error" dot, a colour-coded
chart legend. For the ~8% of men with a colour-vision deficiency (CVD) those can
be indistinguishable, and nothing in the framework could check it. ``cvd_simulate``
adds the two primitives an accessibility / design check needs:

* :func:`simulate_cvd` — map an ``(r, g, b)`` colour through a dichromat
  simulation matrix (protanopia / deuteranopia / tritanopia) at a given
  ``severity`` (0 = unaffected, 1 = full dichromacy).
* :func:`colors_collide` — simulate two colours under a CVD type and report
  whether they become too similar to tell apart (a perceptual ``redmean``
  distance below ``threshold``).

Pure standard library (no numpy / OpenCV) — operates on plain RGB tuples, so it
is fully testable. Imports no ``PySide6``.
"""
import math
from typing import Any, Dict, List, Sequence, Tuple

RGB = Tuple[int, int, int]

# Dichromat simulation matrices (sRGB-space approximation, Brettel/Viénot
# lineage as used by daltonize tooling). Applied at severity 1.0; lower
# severities interpolate toward the identity.
_MATRICES: Dict[str, List[List[float]]] = {
    "protanopia": [[0.567, 0.433, 0.000],
                   [0.558, 0.442, 0.000],
                   [0.000, 0.242, 0.758]],
    "deuteranopia": [[0.625, 0.375, 0.000],
                     [0.700, 0.300, 0.000],
                     [0.000, 0.300, 0.700]],
    "tritanopia": [[0.950, 0.050, 0.000],
                   [0.000, 0.433, 0.567],
                   [0.000, 0.475, 0.525]],
}

# Friendly aliases for the canonical CVD kinds.
_ALIASES = {
    "protan": "protanopia", "protanope": "protanopia", "red": "protanopia",
    "deuter": "deuteranopia", "deutan": "deuteranopia",
    "deuteranope": "deuteranopia", "green": "deuteranopia",
    "tritan": "tritanopia", "tritanope": "tritanopia", "blue": "tritanopia",
}

CVD_KINDS = tuple(_MATRICES)


def _canonical_kind(kind: str) -> str:
    """Resolve a CVD kind name / alias to its canonical key."""
    key = str(kind).strip().lower()
    canonical = _ALIASES.get(key, key)
    if canonical not in _MATRICES:
        raise ValueError(f"unknown CVD kind: {kind!r}")
    return canonical


def _clamp_byte(value: float) -> int:
    """Clamp a channel value to an integer in ``[0, 255]``."""
    return max(0, min(255, int(round(value))))


def simulate_cvd(rgb: Sequence[float], kind: str = "deuteranopia",
                 severity: float = 1.0) -> RGB:
    """Return ``rgb`` as seen under ``kind`` colour-vision deficiency.

    ``severity`` interpolates between the original colour (0) and the full
    dichromat simulation (1). ``rgb`` channels are ``0..255``.
    """
    matrix = _MATRICES[_canonical_kind(kind)]
    strength = max(0.0, min(1.0, float(severity)))
    channels = [float(rgb[0]), float(rgb[1]), float(rgb[2])]
    result = []
    for index in range(3):
        row = matrix[index]
        simulated = row[0] * channels[0] + row[1] * channels[1] \
            + row[2] * channels[2]
        blended = channels[index] * (1.0 - strength) + simulated * strength
        result.append(_clamp_byte(blended))
    return result[0], result[1], result[2]


def color_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """Perceptual ``redmean`` distance between two RGB colours (pure).

    A low-cost approximation of perceived colour difference that weights the
    channels by the average red level.
    """
    red_mean = (float(left[0]) + float(right[0])) / 2.0
    delta_r = float(left[0]) - float(right[0])
    delta_g = float(left[1]) - float(right[1])
    delta_b = float(left[2]) - float(right[2])
    return math.sqrt((2 + red_mean / 256) * delta_r * delta_r
                     + 4 * delta_g * delta_g
                     + (2 + (255 - red_mean) / 256) * delta_b * delta_b)


def colors_collide(left: Sequence[float], right: Sequence[float], *,
                   kind: str = "deuteranopia", severity: float = 1.0,
                   threshold: float = 40.0) -> Dict[str, Any]:
    """Report whether two colours become confusable under ``kind`` CVD.

    Simulates both colours and compares them with :func:`color_distance`;
    ``collide`` is ``True`` when that distance is below ``threshold``. Returns
    ``{collide, distance, kind, severity, simulated_left, simulated_right}``.
    """
    canonical = _canonical_kind(kind)
    strength = max(0.0, min(1.0, float(severity)))
    sim_left = simulate_cvd(left, canonical, strength)
    sim_right = simulate_cvd(right, canonical, strength)
    distance = color_distance(sim_left, sim_right)
    return {
        "collide": distance < float(threshold),
        "distance": round(distance, 3),
        "kind": canonical,
        "severity": strength,
        "simulated_left": list(sim_left),
        "simulated_right": list(sim_right),
    }
