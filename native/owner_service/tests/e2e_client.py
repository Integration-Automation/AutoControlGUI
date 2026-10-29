"""Drive the real C service with the package's Python client, inside the WSL distro.

Usage: python3 -I e2e_client.py <service_e2e> <owner_core_acceptance> <repository root>
Prints one JSON object; exits 0 only when every expectation held.
"""
import json
import subprocess
import sys
import threading
import time

harness, child, repository = sys.argv[1:4]
sys.path.insert(0, repository)
from je_auto_control.utils.agent_runtime.errors import AgentTaskError  # noqa: E402
from je_auto_control.utils.agent_runtime.helper_owner_linux import (  # noqa: E402
    OwnerServiceChannel, SeqpacketTransport)
from je_auto_control.utils.agent_runtime.owner_service_nested import NestedGrant  # noqa: E402

TOP = 1
NESTED = 2
checks = {}
service = subprocess.Popen([harness, child], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
endpoint = service.stdout.readline().strip()


def outcome(function):
    try:
        return "value", function()
    except AgentTaskError as error:
        return "error", str(error)


# 1. Two round trips through socket, lease, START, relay and the helper; then close.
first = OwnerServiceChannel(SeqpacketTransport(endpoint), TOP)
checks["round_trip"] = [first.request("ping", {"n": 1}, timeout=10), first.request("ping", {"n": 2}, timeout=10)]
closed = outcome(first.close)
# A direct fixture is not protected and never reports retirement: the client must refuse to claim it.
checks["unprotected_close"] = closed
checks["unprotected_retired"] = first.retired

# 2. A request waiting for a reply that never comes is stopped by close from another thread.
second = OwnerServiceChannel(SeqpacketTransport(endpoint), TOP)
second.request("ping", {}, timeout=10)
waiting = {}


def hang():
    waiting["result"] = outcome(lambda: second.request("hang", {}, timeout=30))


thread = threading.Thread(target=hang)
thread.start()
time.sleep(0.5)
started = time.monotonic()
checks["concurrent_close"] = outcome(second.close)
thread.join(timeout=10)
checks["close_seconds"] = round(time.monotonic() - started, 2)
checks["waiting_request"] = waiting.get("result")

# 3. The helper exits on its own: the client sees the end of its reply stream.
third = OwnerServiceChannel(SeqpacketTransport(endpoint), TOP)
third.request("ping", {}, timeout=10)
checks["helper_exit"] = outcome(lambda: third.request("exit", {}, timeout=10))

# 4. A nested channel opens with OP_OPEN_CHILD; behind the closed gate no grant exists.
nested = OwnerServiceChannel(SeqpacketTransport(endpoint), NESTED,
                             parent=NestedGrant(((142, 1), (0, 1)), bytes(range(32))))
checks["nested_open"] = outcome(lambda: nested.request("ping", {}, timeout=10))
checks["nested_retired"] = nested.retired

service.stdin.close()
checks["service_report"] = json.loads(service.stdout.readline())
checks["service_exit"] = service.wait(timeout=20)

leases, records = checks["service_report"]["leases"], checks["service_report"]["records"]
expectations = {
    "round_trip": checks["round_trip"] == ["pong", "pong"],
    "unprotected_close_refused": checks["unprotected_close"][0] == "error"
    and "not retired" in checks["unprotected_close"][1],
    "unprotected_not_retired": checks["unprotected_retired"] is False,
    "waiting_request_fenced": checks["waiting_request"] is not None and checks["waiting_request"][0] == "error"
    and "closed" in checks["waiting_request"][1],
    "close_bounded": checks["close_seconds"] < 8,
    "helper_exit_seen": checks["helper_exit"][0] == "error" and "reply stream" in checks["helper_exit"][1],
    "three_leases_closed": len(leases) == 3 and not any(lease["open"] for lease in leases),
    "three_children_dead": len(records) == 3 and all(record["child_dead"] for record in records),
    "no_descriptor_owned": all(record["owned"] == 0 for record in records),
    "service_drained": checks["service_exit"] == 0,
    "nested_refused": checks["nested_open"][0] == "error"
    and "refused to open a lease (status 2" in checks["nested_open"][1],
    "nested_retired_without_helper": checks["nested_retired"] is True,
}
print(json.dumps({"checks": checks, "expectations": expectations}))
sys.exit(0 if all(expectations.values()) else 1)
