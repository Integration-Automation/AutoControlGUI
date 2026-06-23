"""Template-match trustworthiness scoring (second-peak ratio + peak-to-sidelobe)."""
from je_auto_control.utils.match_trust.match_trust import (
    TrustedMatch, match_with_trust, score_peaks,
)

__all__ = ["TrustedMatch", "match_with_trust", "score_peaks"]
