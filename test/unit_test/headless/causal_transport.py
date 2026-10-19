"""Store-backed HTTP boundary fake keeps causal client tests independent of optional web frameworks."""
import json

import je_auto_control as ac


def perform_causal_call(store, call):
    """Model the v3 wire contract; separate optional route tests exercise FastAPI itself."""
    assert call['url'].endswith('/config/alice/causal')
    assert call['follow_redirects'] is False
    if call['method'] == 'GET':
        return {'status': 200, 'text': json.dumps({'version': 3, 'bucket': store.get('alice').to_dict()})}
    body = json.loads(call['body'])
    assert body['version'] == 3
    raw = dict(body['bucket'])
    actor = ac.SyncActor.from_dict(raw.pop('_actor'))
    try:
        revision = store.commit('alice', ac.CausalBucket.from_dict(raw), base_revision=body['base_revision'],
                                operation_id=body['operation_id'], actor=actor)
    except ac.ConfigRevisionConflict as error:
        detail = {'code': error.code, 'revision': error.current_revision, 'message': str(error)}
        return {'status': 409, 'text': json.dumps({'detail': detail})}
    except ac.FullResyncRequired as error:
        return {'status': 409, 'text': json.dumps({'detail': {'code': 'full_resync_required', 'message': str(error)}})}
    return {'status': 200, 'text': json.dumps({'version': 3, 'revision': revision,
                                             'bucket': store.get('alice').to_dict()})}
