"""Feature-flag evaluation with targeting rules and deterministic rollout."""
from je_auto_control.utils.feature_flags.feature_flags import (
    Flag, FlagStore, assign_variant, evaluate_flag, is_enabled,
    percentage_bucket,
)

__all__ = [
    "Flag", "FlagStore", "assign_variant", "evaluate_flag", "is_enabled",
    "percentage_bucket",
]
