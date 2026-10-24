"""An actually terminated owned coordinator cannot replay old durable DAG deliveries on restart."""
import json
import os
import subprocess
import sys
from pathlib import Path

from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from .test_agent_dag_background import until
from .test_agent_dag_batches import graph

SCRIPT = '''
import json, os, sys, threading
from pathlib import Path
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
root = Path(sys.argv[1])
service = AgentRuntimeService(root, targets={'fixture': object()})
service.start()
service._dag_jobs._drain = lambda: service._dag_jobs._stop.wait()
definition = json.loads(sys.argv[2])
batch = service.runtime.batches.control('register', {'definition': definition})
service.runtime.batches.control('run_background', {'batch_id': batch['batch_id'],
    'definition': definition, 'max_parallel': 4})
with service.runtime.store.connection() as connection:
    delivery = json.loads(connection.execute("SELECT data FROM work_items WHERE queue='agent_dag'").fetchone()[0])
service.runtime.batches.control('claim', {'batch_id': batch['batch_id'],
    'attempt': delivery['started']['attempt'], 'node_id': 'a'})
(root / 'ready.json').write_text(json.dumps(batch))
while not (root / 'crash').exists():
    threading.Event().wait(0.02)
os._exit(71)
'''


def test_process_death_retires_old_delivery_and_preserves_unknown_claim(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]))
    process = subprocess.Popen([sys.executable, '-u', '-c', SCRIPT, str(tmp_path), json.dumps(graph())],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        until(lambda: (tmp_path / 'ready.json').exists() or process.poll() is not None)
        assert process.poll() is None
        batch = json.loads((tmp_path / 'ready.json').read_text())
        (tmp_path / 'crash').touch()
        assert process.wait(timeout=10) == 71
        service = AgentRuntimeService(tmp_path, targets={'fixture': object()})
        try:
            service.start()
            result = service.runtime.batches.control('get', {'batch_id': batch['batch_id']})
            assert result['state'] == 'waiting_review' and result['background']['state'] == 'failed'
            assert result['nodes'][0]['phase'] == 'claimed' and service.runtime.list() == []
            review = service.runtime.batches.control('review_continuation', {
                'batch_id': batch['batch_id'], 'definition': graph()})
            assert not review['can_approve'] and review['decisions'][0]['action'] == 'wait'
        finally:
            service.close()
    finally:
        if process.poll() is None:
            (tmp_path / 'crash').touch()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        process.stderr.close()
