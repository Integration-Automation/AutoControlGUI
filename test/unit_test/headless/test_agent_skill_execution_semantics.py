"""Original effect comparison distinguishes JSON booleans, numbers and expected results."""
import pytest

from headless.test_agent_skill_execution import edit
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.skill_recording import verified_skill_actions


@pytest.mark.parametrize('field', ['arguments', 'result'])
@pytest.mark.parametrize('expected,actual', [(True, 1), (False, 0), (1, 1.0)])
def test_exact_skill_evidence_does_not_conflate_json_types(field, expected, actual):
    action = edit('Value', expected if field == 'arguments' else 'value')
    if field == 'result':
        action['expect_result'] = expected
    arguments = edit('Value', actual if field == 'arguments' else 'value')['arguments']
    receipt = {'command': 'AC_edit', 'arguments': arguments,
               'status': 'confirmed', 'result': actual}
    spec = {'goal': 'Compare exact original effects', 'mode': 'skill', 'target': 'editor',
            'apps': ['Editor'], 'allowed_tools': ['AC_edit'], 'actions': [action],
            'success_criteria': [{'kind': 'actions_complete'}]}
    with pytest.raises(AgentTaskError, match='semantic plan'):
        verified_skill_actions(spec, [receipt], complete=True)
