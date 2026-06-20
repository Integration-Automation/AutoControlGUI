"""DMN-style decision tables: rules + hit policy for externalized branching."""
from je_auto_control.utils.decision_table.decision_table import (
    DecisionTable, Rule, evaluate_table,
)

__all__ = ["DecisionTable", "Rule", "evaluate_table"]
