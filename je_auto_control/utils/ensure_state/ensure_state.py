"""Idempotently bring a control or setting to a desired state: read, act, verify.

Automation that *acts unconditionally* — "click the checkbox", "type the value"
— double-toggles a box that was already checked, or re-enters a field that was
already correct, and can't be safely re-run. The robust shape is
read-compare-act-verify: look at the current state, do nothing if it already
matches, otherwise apply the change and confirm it took. ``ensure_state`` is
that primitive.

* :func:`ensure_state` — generic: read via ``reader``, and if it doesn't equal
  ``desired`` apply ``setter`` and re-read, up to ``attempts`` times.
* :func:`ensure_toggle` — the boolean specialization for a stateless flip: read
  ``is_on`` and call ``toggle`` only while it differs from ``desired``.

A control already in the desired state is left untouched (``changed=False``),
so the call is idempotent and safe to re-run. The reader / setter / toggle seams
are injectable, so the logic is fully testable without a real control. Distinct
from :mod:`idempotency` (a request-key replay cache) — this converges *device
state*, not call results. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict

StateReader = Callable[[], Any]
StateSetter = Callable[[Any], None]
StateEquals = Callable[[Any, Any], bool]


def _default_equals(left: Any, right: Any) -> bool:
    """Default equality used to decide whether the state already matches."""
    return left == right


def ensure_state(desired: Any, *, reader: StateReader, setter: StateSetter,
                 equals: StateEquals = _default_equals,
                 attempts: int = 2) -> Dict[str, Any]:
    """Bring the state read by ``reader`` to ``desired`` via ``setter`` (idempotent).

    Reads the current state; if ``equals(current, desired)`` it returns
    immediately with ``changed=False``. Otherwise it applies ``setter(desired)``
    and re-reads, up to ``attempts`` times. Returns
    ``{ok, changed, value, attempts}``.
    """
    current = reader()
    if equals(current, desired):
        return {"ok": True, "changed": False, "value": current, "attempts": 0}
    used = 0
    for used in range(1, max(1, int(attempts)) + 1):
        setter(desired)
        current = reader()
        if equals(current, desired):
            return {"ok": True, "changed": True, "value": current,
                    "attempts": used}
    return {"ok": False, "changed": True, "value": current, "attempts": used}


def ensure_toggle(desired: bool, *, is_on: Callable[[], bool],
                  toggle: Callable[[], None],
                  attempts: int = 2) -> Dict[str, Any]:
    """Bring a boolean toggle to ``desired`` by flipping only while it differs.

    ``is_on`` reads the current boolean; ``toggle`` performs a stateless flip and
    is called only when the state does not already match ``desired``. Returns
    ``{ok, changed, value, attempts}``.
    """
    return ensure_state(bool(desired), reader=lambda: bool(is_on()),
                        setter=lambda _desired: toggle(), attempts=attempts)
