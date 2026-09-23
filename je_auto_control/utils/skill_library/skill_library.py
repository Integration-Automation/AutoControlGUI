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
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from je_auto_control.utils.json_store import SharedJsonDict


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


def _as_tags(tags: Any) -> List[str]:
    """A bare string is one tag -- ``list("login")`` stored its letters."""
    if isinstance(tags, str):
        return [tags]
    return [str(tag) for tag in tags or []]


class SkillLibrary:
    """A JSON-backed store of named action sequences.

    Every change re-reads the file under a lock and writes it atomically, so
    two libraries (or processes) on one file no longer drop each other's
    saves; a file that is not a JSON object raises instead of being erased.
    """

    def __init__(self, path: str) -> None:
        self._state = SharedJsonDict(path, strict=True)
        self._state.read()          # a corrupt library fails here, as before

    @property
    def _items(self) -> Dict[str, Dict[str, Any]]:
        return {str(key): dict(value) for key, value in self._state.read().items()}

    def save(self, name: str, actions: List[Any], *, description: str = "",
             tags: Optional[List[str]] = None) -> Skill:
        """Store (or overwrite) a skill; ``actions`` must be a non-empty list."""
        if not isinstance(actions, list) or not actions:
            raise ValueError("a skill needs a non-empty list of actions")
        record = {"actions": list(actions), "description": str(description),
                  "tags": _as_tags(tags), "updated": time.time()}
        self._state.update(lambda items: items.__setitem__(str(name), record))
        return _to_skill(str(name), record)

    def get(self, name: str) -> Optional[Skill]:
        """Return the skill named ``name`` or ``None``."""
        raw = self._items.get(str(name))
        return _to_skill(str(name), raw) if raw is not None else None

    def remove(self, name: str) -> bool:
        """Delete a skill; return whether it existed."""
        return self._state.update(lambda items: items.pop(str(name), None) is not None)

    def names(self) -> List[str]:
        """Return the saved skill names, sorted."""
        return sorted(self._items)

    def search(self, query: str) -> List[Skill]:
        """Return skills whose name, description or tags match ``query``."""
        needle = str(query).lower().strip()
        items = self._items
        matches = [name for name, raw in items.items()
                   if _skill_matches(name, raw, needle)]
        return [_to_skill(name, items[name]) for name in sorted(matches)]

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
