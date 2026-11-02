"""Contract samples must include the keys promised by TypedDict returns."""
from typing import TypedDict

import pytest

from headless._contract_sweep import _value_for
from je_auto_control.utils.action_journal.capture import JournalRunResult


class _OptionalPart(TypedDict, total=False):
    optional_label: str


class _RequiredPart(_OptionalPart):
    count: int


class _Recursive(TypedDict):
    child: "_Recursive"


def test_real_journal_contract_includes_all_guaranteed_fields():
    assert _value_for(JournalRunResult) == {
        "run_id": "", "journal_path": "", "record": {}, "failed_actions": 0}


def test_inherited_optional_fields_are_not_promised():
    assert _value_for(_RequiredPart) == {"count": 0}


def test_required_cycles_are_refused_without_fabricating_a_value():
    with pytest.raises(ValueError, match="self-referential"):
        _value_for(_Recursive)
