"""Portable transfer selections and manifests reject ambiguous or authority-bearing wire data."""
from dataclasses import FrozenInstanceError
import importlib
import importlib.util

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def selection_type():
    module_name = 'je_auto_control.utils.agent_runtime.transfer_models'
    assert importlib.util.find_spec(module_name) is not None, 'transfer selection model is not implemented'
    module = importlib.import_module(module_name)
    selected = getattr(module, 'TransferSelection', None)
    assert selected is not None, 'TransferSelection is not implemented'
    return selected


def test_selection_round_trips_an_immutable_detached_criterion_selection():
    original = {'criterion': 2, 'names': ['report.csv']}
    selection = selection_type().from_dict(original)
    original['names'].append('unselected.csv')

    assert selection.criterion == 2
    assert selection.names == ('report.csv',)
    assert selection.to_dict() == {'criterion': 2, 'names': ['report.csv']}
    exported = selection.to_dict()
    exported['names'].append('another.csv')
    assert selection.names == ('report.csv',)
    with pytest.raises(FrozenInstanceError):
        selection.criterion = 3


@pytest.mark.parametrize('value', [
    {'criterion': True, 'names': []},
    {'criterion': 1.0, 'names': []},
    {'criterion': -1, 'names': []},
    {'criterion': '1', 'names': []},
    {'criterion': None, 'names': []},
    {},
    {'criterion': 0, 'names': [], 'principal': {'user_id': 'foreign'}},
    {'criterion': 0, 'names': 'report.csv'},
    {'criterion': 0, 'names': ('report.csv',)},
    {'criterion': 0, 'names': {'report.csv': 1}},
    {'criterion': 0, 'names': None},
    {'criterion': 0, 'names': [False]},
    {'criterion': 0, 'names': [[]]},
    {'criterion': 0, 'names': ['']},
    {'criterion': 0, 'names': ['../report.csv']},
    {'criterion': 0, 'names': ['folder/report.csv']},
    {'criterion': 0, 'names': ['C:\\report.csv']},
    {'criterion': 0, 'names': ['one.csv', 'ONE.csv']},
    {'criterion': 0, 'names': ['CON']},
    {'criterion': 0, 'names': ['*.csv']},
    {'criterion': 0, 'names': ['file.']},
    {'criterion': 0, 'names': ['..\\report.csv']},
    {'criterion': 0, 'names': ['e\u0301.csv', '\u00e9.csv']},
    {'criterion': 0, 'names': ['a.csv', 'a.csv']},
    {'criterion': 0, 'names': ['nul\x00.csv']},
    {'criterion': 0, 'names': [f'{number}.csv' for number in range(501)]},
    None, [], True,
])
def test_selection_rejects_ambiguous_or_nonportable_wire_objects(value):
    with pytest.raises(AgentTaskError):
        selection_type().from_dict(value)


@pytest.mark.parametrize(('criterion', 'names'), [
    (True, ()), (-1, ()), (0, ['report.csv']), (0, ('../report.csv',)),
])
def test_selection_constructor_keeps_the_same_immutable_value_bounds(criterion, names):
    with pytest.raises(AgentTaskError):
        selection_type()(criterion, names)


@pytest.mark.parametrize('names', [[], ['報告.csv'], ['e\u0301.csv']])
def test_selection_preserves_valid_empty_and_unicode_name_values(names):
    value = {'criterion': 0, 'names': names}
    assert selection_type().from_dict(value).to_dict() == value
