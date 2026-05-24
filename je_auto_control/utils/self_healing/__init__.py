"""Self-healing locators: image-template first, VLM fallback.

Public surface:

* :func:`self_heal_locate` — return resolved screen coordinates or a
  miss outcome without raising;
* :func:`self_heal_click` — same, then click the resolved point;
* :class:`HealOutcome` — structured result both helpers return;
* :data:`default_heal_log` — singleton JSON-lines log every heal
  attempt is appended to (override per-call via ``log=`` argument).
"""
from je_auto_control.utils.self_healing.heal_log import (
    HealEvent, HealEventLog, default_heal_log,
)
from je_auto_control.utils.self_healing.locator import (
    HealOutcome, SelfHealError,
    METHOD_IMAGE, METHOD_MISS, METHOD_VLM,
    self_heal_click, self_heal_locate,
)


__all__ = [
    "HealEvent", "HealEventLog", "HealOutcome", "SelfHealError",
    "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM",
    "default_heal_log", "self_heal_click", "self_heal_locate",
]
