"""Protected nested-parent payload: a JSON-lines helper that opens its own child lease.

Runs as the payload account inside its record's payload cgroup, started by the service
with argv [python3, -I, this file, <repository>, <endpoint>]. Requests:
  nest   read the grant from fd 4, open an OPEN_CHILD lease, start the child, and reply
         with the child's `ping` and `escape` results;
  close  close the child channel and reply whether it retired.
"""
import json
import sys

sys.path.insert(0, sys.argv[1])
from je_auto_control.utils.agent_runtime.errors import AgentTaskError  # noqa: E402
from je_auto_control.utils.agent_runtime.helper_owner_linux import (  # noqa: E402
    OwnerServiceChannel, SeqpacketTransport)
from je_auto_control.utils.agent_runtime.owner_service_nested import read_nested_bootstrap  # noqa: E402

ENDPOINT = sys.argv[2]
NESTED_POLICY = 2
grant = read_nested_bootstrap()
child = None


def answer(request_id, result=None, error=None):
    message = {"id": request_id, "result": result} if error is None else {"id": request_id, "error": error}
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    request = json.loads(line)
    try:
        if request["operation"] == "nest":
            if grant is None:
                raise AgentTaskError("no nested grant was delivered on fd 4")
            child = OwnerServiceChannel(SeqpacketTransport(ENDPOINT), NESTED_POLICY, parent=grant)
            answer(request["id"], {"ping": child.request("ping", {}, timeout=20),
                                   "escaped": child.request("escape", {}, timeout=20)})
        elif request["operation"] == "close":
            child.close()
            answer(request["id"], {"retired": child.retired})
        else:
            answer(request["id"], "pong")
    except AgentTaskError as error:
        answer(request["id"], error=str(error))
