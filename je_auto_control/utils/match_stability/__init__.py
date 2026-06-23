"""Pre-match settle gating and match persistence over a sequence of frames."""
from je_auto_control.utils.match_stability.match_stability import (
    match_persistence, region_stability,
)

__all__ = ["region_stability", "match_persistence"]
