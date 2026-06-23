"""Multi-template consensus matching (vote several references onto one location)."""
from je_auto_control.utils.match_ensemble.match_ensemble import (
    match_ensemble, vote_centers,
)

__all__ = ["match_ensemble", "vote_centers"]
