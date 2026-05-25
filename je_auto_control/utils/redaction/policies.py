"""Redaction policy: which rules to apply before a screenshot leaves the host.

A :class:`RedactionPolicy` is a plain data record so callers can build
one on the fly (CLI, REST, MCP) without instantiating Python helpers.
Three built-in policies cover the common cases:

* :data:`POLICY_OFF` — pass screenshots through untouched. Useful in
  fully-trusted lab environments and for opt-in upgrades.
* :data:`POLICY_STRICT` — every built-in detector enabled (email,
  credit-card, SSN, phone, password fields). Default when the
  ``JE_AUTOCONTROL_REDACTION=strict`` env var is set.
* :data:`POLICY_MODERATE` — only password fields + credit-card +
  email. Lighter touch suitable for shared dev environments.

Callers can pass explicit ``regions`` (absolute screen rectangles) to
unconditionally blur — useful for sticky overlays the rules don't
otherwise know about (e.g. the user's wallet popup).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# Detector tag constants (avoid magic strings in the engine + tests).
DETECTOR_EMAIL = "email"
DETECTOR_CREDIT_CARD = "credit_card"
DETECTOR_SSN = "ssn"
DETECTOR_PHONE = "phone"
DETECTOR_PASSWORD_FIELD = "password_field"


@dataclass(frozen=True)
class RedactionPolicy:
    """Declarative description of what to redact in a screenshot.

    ``detectors`` is the set of named rule families to enable. Unknown
    names are ignored (so future detectors don't break older policies
    serialised to disk). ``regions`` are forced-blur rectangles in
    absolute screen pixels ``(x1, y1, x2, y2)``.
    """

    detectors: Tuple[str, ...] = ()
    regions: Tuple[Tuple[int, int, int, int], ...] = ()
    blur_radius: int = 16
    overlay_color: Optional[Tuple[int, int, int]] = None

    def with_extra_regions(
            self, extras: List[Tuple[int, int, int, int]]) -> "RedactionPolicy":
        """Return a policy with ``extras`` appended to ``regions``."""
        return RedactionPolicy(
            detectors=tuple(self.detectors),
            regions=tuple(self.regions) + tuple(tuple(r) for r in extras),
            blur_radius=self.blur_radius,
            overlay_color=self.overlay_color,
        )

    def to_dict(self) -> dict:
        """JSON-safe snapshot for transport over the REST / MCP wire."""
        return {
            "detectors": list(self.detectors),
            "regions": [list(r) for r in self.regions],
            "blur_radius": int(self.blur_radius),
            "overlay_color": (list(self.overlay_color)
                              if self.overlay_color is not None else None),
        }


POLICY_OFF = RedactionPolicy()

POLICY_STRICT = RedactionPolicy(
    detectors=(
        DETECTOR_EMAIL, DETECTOR_CREDIT_CARD, DETECTOR_SSN,
        DETECTOR_PHONE, DETECTOR_PASSWORD_FIELD,
    ),
)

POLICY_MODERATE = RedactionPolicy(
    detectors=(
        DETECTOR_EMAIL, DETECTOR_CREDIT_CARD, DETECTOR_PASSWORD_FIELD,
    ),
)


def policy_from_name(name: Optional[str]) -> RedactionPolicy:
    """Look up a built-in policy by name (case-insensitive); ``None`` → OFF."""
    if name is None:
        return POLICY_OFF
    canon = name.strip().lower()
    table = {
        "off": POLICY_OFF, "none": POLICY_OFF, "": POLICY_OFF,
        "strict": POLICY_STRICT, "high": POLICY_STRICT,
        "moderate": POLICY_MODERATE, "medium": POLICY_MODERATE,
    }
    if canon not in table:
        raise ValueError(
            f"unknown redaction policy: {name!r}; expected one of "
            f"{sorted(set(table))}",
        )
    return table[canon]


__all__ = [
    "DETECTOR_CREDIT_CARD", "DETECTOR_EMAIL", "DETECTOR_PASSWORD_FIELD",
    "DETECTOR_PHONE", "DETECTOR_SSN",
    "POLICY_MODERATE", "POLICY_OFF", "POLICY_STRICT",
    "RedactionPolicy", "policy_from_name",
]
