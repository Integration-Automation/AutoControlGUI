"""Persistent library of named, reusable action sequences ("skills").

Agents and authors accumulate playbooks — "log in", "export the report",
"dismiss the cookie banner". A :class:`SkillLibrary` stores each as a
named action sequence on disk so it can be recalled, searched, and
replayed across runs, instead of re-deriving the steps every time. This
is the durable counterpart to the in-memory macro registry.

Pure standard library (JSON storage); imports no ``PySide6``. The
executor is imported lazily so storage and search work headless on any
platform.
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Skill:
    """A named, reusable action sequence with metadata."""
    name: str
    actions: List[Any]
    description: str = ""
    tags: List[str] = field(default_factory=list)
    updated: float = 0.0


def _to_skill(name: str, raw: Dict[str, Any]) -> Skill:
    return Skill(name=name, actions=list(raw.get("actions") or []),
                 description=str(raw.get("description") or ""),
                 tags=list(raw.get("tags") or []),
                 updated=float(raw.get("updated") or 0.0))


class SkillLibrary:
    """A JSON-backed store of named action sequences."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._items: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{self._path} is not a skill library")
        return {str(k): dict(v) for k, v in data.items()}

    def _flush(self) -> None:
        self._path.write_text(
            json.dumps(self._items, indent=2, ensure_ascii=False),
            encoding="utf-8")

    def save(self, name: str, actions: List[Any], *, description: str = "",
             tags: Optional[List[str]] = None) -> Skill:
        """Store (or overwrite) a skill; ``actions`` must be a non-empty list."""
        if not isinstance(actions, list) or not actions:
            raise ValueError("a skill needs a non-empty list of actions")
        record = {"actions": list(actions), "description": str(description),
                  "tags": list(tags or []), "updated": time.time()}
        self._items[str(name)] = record
        self._flush()
        return _to_skill(str(name), record)

    def get(self, name: str) -> Optional[Skill]:
        """Return the skill named ``name`` or ``None``."""
        raw = self._items.get(str(name))
        return _to_skill(str(name), raw) if raw is not None else None

    def remove(self, name: str) -> bool:
        """Delete a skill; return whether it existed."""
        existed = str(name) in self._items
        if existed:
            del self._items[str(name)]
            self._flush()
        return existed

    def names(self) -> List[str]:
        """Return the saved skill names, sorted."""
        return sorted(self._items)

    def search(self, query: str) -> List[Skill]:
        """Return skills whose name, description or tags match ``query``."""
        needle = str(query).lower().strip()
        matches = [name for name, raw in self._items.items()
                   if _skill_matches(name, raw, needle)]
        return [_to_skill(name, self._items[name]) for name in sorted(matches)]

    def run(self, name: str, *, executor: Any = None) -> Dict[str, Any]:
        """Execute a stored skill's actions; return the execution record."""
        skill = self.get(name)
        if skill is None:
            raise KeyError(f"no skill named {name!r}")
        runner = executor
        if runner is None:
            from je_auto_control.utils.executor.action_executor import executor \
                as default_executor
            runner = default_executor
        return runner.execute_action(skill.actions)


def _skill_matches(name: str, raw: Dict[str, Any], needle: str) -> bool:
    if not needle:
        return True
    haystack = " ".join([name, str(raw.get("description") or ""),
                         " ".join(raw.get("tags") or [])]).lower()
    return needle in haystack
