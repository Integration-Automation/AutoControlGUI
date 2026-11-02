"""Every linked execution snapshot uses the same ordering as the real recovery admission witness."""
from headless.test_agent_skill_execution import execution as _execution, successor, edit
from je_auto_control.utils.agent_runtime.runner import run_task

execution = _execution


def test_adjacent_chain_segments_share_the_identical_snapshot_after_multiple_receipt_reviews(execution):
    runtime = execution.runtime
    trial = runtime.skills.control('validate', {'candidate_id': execution.candidate['id']})
    runtime.pause(trial['task_id'])
    middle = successor(runtime, trial['task_id'])['task_id']
    runtime.pause(middle)
    attempts = []
    for _index in range(2):
        attempt = runtime.store.prepare(middle, 'AC_edit', edit('Never applied', 'pending')['arguments'])
        runtime.store.settle(attempt, 'dispatched')
        runtime.store.settle(attempt, 'uncertain')
        attempts.append(attempt)
    # Reverse lexical insertion differs deterministically from recovery's ORDER BY action_id witness.
    for attempt in sorted(attempts, reverse=True):
        runtime.reconcile(middle, {'action_id': attempt, 'decision': 'not_applied',
                                  'note': 'Independently confirmed the attempted input was not applied'})
    leaf = successor(runtime, middle)['task_id']
    assert run_task(runtime, leaf).state == 'succeeded'
    request = {'candidate_id': execution.candidate['id'], 'task_id': trial['task_id'], 'execution_task_id': leaf}
    review = runtime.skills.control('review_execution', request)
    segments = review['evidence']['segments']
    assert len(segments) == 2
    assert segments[0]['snapshot'] == segments[1]['source_snapshot']
