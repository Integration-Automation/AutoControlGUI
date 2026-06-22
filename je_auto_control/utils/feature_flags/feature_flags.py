"""Runtime feature flags with targeting rules and deterministic rollout.

``decision_table`` is a one-shot DMN evaluator and ``ab_locator`` measures
locator outcomes — neither is a product feature-flag store with sticky
percentage rollout. This adds an OpenFeature-shaped flag engine: typed flags
with targeting rules, weighted variants, a kill switch, and consistent-hash
bucketing so a given subject always lands in the same variant.

Pure standard library (``hashlib`` + ``re`` + ``json``); deterministic;
imports no ``PySide6``.
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


def _semver(value: Any) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", str(value))[:3])


_OPS = {
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b, "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b,
    "in": lambda a, b: a in b, "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a,
    "semver_gt": lambda a, b: _semver(a) > _semver(b),
    "semver_ge": lambda a, b: _semver(a) >= _semver(b),
    "semver_lt": lambda a, b: _semver(a) < _semver(b),
}


@dataclass(frozen=True)
class Flag:
    """A single feature flag definition."""

    key: str
    variants: Dict[str, Any] = field(default_factory=dict)
    default_variant: str = ""
    off_variant: str = ""
    enabled: bool = True
    targeting: tuple = ()
    fallthrough: Any = None


class FlagStore:
    """An in-memory set of feature flags (plain data, injectable)."""

    def __init__(self, flags: Mapping[str, Flag]) -> None:
        self._flags = dict(flags)

    def get(self, key: str) -> Optional[Flag]:
        """Return the flag named ``key`` or ``None``."""
        return self._flags.get(key)

    @classmethod
    def from_dict(cls, spec: Mapping[str, Any]) -> "FlagStore":
        """Build a store from a ``{"flags": {...}}`` (or bare) mapping."""
        raw = spec.get("flags", spec) if isinstance(spec, Mapping) else {}
        flags = {}
        for key, body in (raw or {}).items():
            flags[key] = Flag(
                key=key,
                variants=dict(body.get("variants", {})),
                default_variant=body.get("default_variant", ""),
                off_variant=body.get("off_variant",
                                     body.get("default_variant", "")),
                enabled=bool(body.get("enabled", True)),
                targeting=tuple(body.get("targeting", ())),
                fallthrough=body.get("fallthrough"),
            )
        return cls(flags)

    @classmethod
    def from_file(cls, path: str) -> "FlagStore":
        """Load a flag store from a JSON file (path is realpath-checked)."""
        safe = os.path.realpath(path)
        with open(safe, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))


def percentage_bucket(key: str, context_key: str, *, salt: str = "",
                      buckets: int = 100) -> int:
    """Return a stable bucket in ``[0, buckets)`` for (key, context_key)."""
    basis = f"{key}.{salt}.{context_key}".encode("utf-8")
    digest = hashlib.sha256(basis).hexdigest()[:15]
    return int(digest, 16) % max(1, buckets)


def assign_variant(key: str, weights: Mapping[str, int], context_key: str, *,
                   salt: str = "") -> str:
    """Deterministically pick a weighted variant for ``context_key``."""
    total = sum(weights.values())
    if total <= 0:
        return next(iter(weights))
    bucket = percentage_bucket(key, context_key, salt=salt, buckets=total)
    cumulative = 0
    name = ""
    for name, weight in weights.items():
        cumulative += weight
        if bucket < cumulative:
            return name
    return name


def _rule_matches(rule: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    for attr, condition in rule.get("conditions", {}).items():
        operator = _OPS.get(condition.get("op", "eq"))
        if operator is None:
            return False
        try:
            if not operator(context.get(attr), condition.get("value")):
                return False
        except TypeError:
            return False
    return True


def _result(flag: Flag, variant: str, reason: str) -> Dict[str, Any]:
    return {"flag_key": flag.key, "variant": variant,
            "value": flag.variants.get(variant), "reason": reason}


def _context_key(context: Mapping[str, Any]) -> str:
    return str(context.get("targeting_key") or context.get("key") or "")


def _serve(flag: Flag, serve: Any, context: Mapping[str, Any],
           reason: str) -> Dict[str, Any]:
    if isinstance(serve, Mapping) and "rollout" in serve:
        variant = assign_variant(flag.key, serve["rollout"],
                                 _context_key(context))
        return _result(flag, variant, "SPLIT")
    return _result(flag, serve, reason)


def evaluate_flag(store: FlagStore, key: str,
                  context: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate ``key`` for ``context``; return {value, variant, reason}."""
    context = context or {}
    flag = store.get(key)
    if flag is None:
        return {"flag_key": key, "variant": None, "value": None,
                "reason": "ERROR"}
    if not flag.enabled:
        return _result(flag, flag.off_variant, "DISABLED")
    for rule in flag.targeting:
        if _rule_matches(rule, context):
            return _serve(flag, rule.get("serve"), context, "TARGETING_MATCH")
    if flag.fallthrough is not None:
        return _serve(flag, flag.fallthrough, context, "DEFAULT")
    return _result(flag, flag.default_variant, "DEFAULT")


def is_enabled(store: FlagStore, key: str,
               context: Optional[Mapping[str, Any]] = None,
               default: bool = False) -> bool:
    """Boolean shortcut over :func:`evaluate_flag`."""
    value = evaluate_flag(store, key, context).get("value")
    return default if value is None else bool(value)
