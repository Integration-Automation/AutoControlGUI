"""Evaluate inputs against a table of rules (a DMN-style decision table).

Nested ``AC_if_var`` chains get unreadable fast; a decision table externalizes
branching into rows of ``conditions -> outputs`` with a *hit policy*. Each cell
condition is a wildcard (``None`` / ``"-"`` / ``"*"``), a literal (equality), or
``{"op": "ge", "value": 18}`` using the project's standard comparators
(``eq/ne/lt/le/gt/ge/contains/startswith/endswith`` — reused from the executor,
not duplicated).

Hit policies: ``UNIQUE`` (exactly one rule may match, else error), ``FIRST`` /
``PRIORITY`` (first matching rule wins), ``COLLECT`` (all matches). Pure standard
library; imports no ``PySide6``.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

HIT_UNIQUE = "UNIQUE"
HIT_FIRST = "FIRST"
HIT_PRIORITY = "PRIORITY"
HIT_COLLECT = "COLLECT"
_WILDCARDS = (None, "", "-", "*")


@dataclass
class Rule:
    """One table row: per-input conditions and the outputs to return."""

    conditions: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)


def _comparators() -> Dict[str, Any]:
    from je_auto_control.utils.executor.flow_control import _COMPARATORS
    return _COMPARATORS


def _cell_matches(value: Any, condition: Any) -> bool:
    if condition in _WILDCARDS:
        return True
    if isinstance(condition, dict) and "op" in condition:
        comparator = _comparators().get(condition["op"])
        if comparator is None:
            raise ValueError(f"unknown decision op: {condition['op']!r}")
        try:
            return comparator(value, condition.get("value"))
        except TypeError:
            return False
    return value == condition


def _rule_matches(rule: Rule, context: Mapping[str, Any]) -> bool:
    return all(_cell_matches(context.get(name), cond)
               for name, cond in rule.conditions.items())


class DecisionTable:
    """A list of rules evaluated against an input context by a hit policy."""

    def __init__(self, inputs: List[str], rules: List[Rule],
                 hit_policy: str = HIT_UNIQUE) -> None:
        """``inputs`` documents the input names; ``hit_policy`` selects matches."""
        self.inputs = list(inputs)
        self.rules = list(rules)
        self.hit_policy = hit_policy.upper()

    @classmethod
    def from_dict(cls, spec: Mapping[str, Any]) -> "DecisionTable":
        """Build a table from a JSON-style ``{inputs, hit_policy, rules}`` spec."""
        rules = [Rule(dict(r.get("conditions", {})), dict(r.get("outputs", {})))
                 for r in spec.get("rules", [])]
        return cls(spec.get("inputs", []), rules,
                   spec.get("hit_policy", HIT_UNIQUE))

    def evaluate(self, context: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """Return the outputs of matching rules per the hit policy."""
        matches = [dict(rule.outputs) for rule in self.rules
                   if _rule_matches(rule, context)]
        if self.hit_policy == HIT_UNIQUE and len(matches) > 1:
            raise ValueError(
                f"UNIQUE hit policy matched {len(matches)} rules")
        if self.hit_policy in (HIT_FIRST, HIT_PRIORITY, HIT_UNIQUE):
            return matches[:1]
        return matches


def evaluate_table(spec: Mapping[str, Any],
                   context: Mapping[str, Any]) -> Any:
    """Evaluate a table spec against a context.

    Returns a list for ``COLLECT``; otherwise the single matched outputs dict
    (or ``{}`` when nothing matches).
    """
    table = DecisionTable.from_dict(spec)
    matches = table.evaluate(context)
    if table.hit_policy == HIT_COLLECT:
        return matches
    return matches[0] if matches else {}
