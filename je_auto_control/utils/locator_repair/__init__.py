"""Self-healing write-back: persist corrected locators from heal events."""
from je_auto_control.utils.locator_repair.locator_repair import (
    RepairStore, RepairSuggestion, repair_from_heal,
)

__all__ = ["RepairStore", "RepairSuggestion", "repair_from_heal"]
