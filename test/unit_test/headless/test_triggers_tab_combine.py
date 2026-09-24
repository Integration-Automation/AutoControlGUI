"""The combining logic behind the Triggers tab's three combine buttons.

``_on_combine`` was the one function in the package over the complexity limit,
and the part worth testing — which selected ids become a composite's children —
needed no Qt at all. It is a module function now, so this test does not build a
widget; only the import needs PySide6.
"""
from dataclasses import dataclass

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from je_auto_control.gui.triggers_tab import (  # noqa: E402
    COMPOSITE_BY_MODE, children_to_combine,
)
from je_auto_control.utils.triggers.trigger_engine import (  # noqa: E402
    AllOfTrigger, AnyOfTrigger, SequenceTrigger,
)


@dataclass
class _Trigger:
    trigger_id: str


def test_selected_ids_become_children_in_the_order_given():
    triggers = [_Trigger("a"), _Trigger("b"), _Trigger("c")]
    children = children_to_combine(["c", "a"], triggers)
    assert [child.trigger_id for child in children] == ["c", "a"]


def test_an_id_that_no_longer_exists_is_dropped():
    """The table can outlive a removal; the stale row must not raise."""
    triggers = [_Trigger("a"), _Trigger("b")]
    children = children_to_combine(["a", "gone", "b"], triggers)
    assert [child.trigger_id for child in children] == ["a", "b"]


@pytest.mark.parametrize("ids", [[], ["a"], ["a", "gone"], ["gone", "other"]])
def test_fewer_than_two_resolved_triggers_combine_into_nothing(ids):
    assert children_to_combine(ids, [_Trigger("a")]) == []


def test_every_button_mode_maps_to_its_composite():
    assert COMPOSITE_BY_MODE == {
        "all": AllOfTrigger, "any": AnyOfTrigger, "sequence": SequenceTrigger,
    }
