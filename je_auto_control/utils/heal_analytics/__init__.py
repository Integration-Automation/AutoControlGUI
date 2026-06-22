"""Analytics over the self-healing event log (heal rate, brittle locators)."""
from je_auto_control.utils.heal_analytics.heal_analytics import (
    analyze_heal_log, heal_stats,
)

__all__ = ["analyze_heal_log", "heal_stats"]
