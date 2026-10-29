"""Protected acceptance client, run as a real account inside WSL.

Usage: python3 -I protected_client.py <repository root> <endpoint> hold|foreign
hold: one request through a protected payload, then `escape`, printing both; then it
      serves commands on stdin, one per line: `ping` makes another request, `close`
      closes and prints whether the service observed the helper retired.
foreign: try the same as an account the guardian does not list.
"""
import json
import sys

sys.path.insert(0, sys.argv[1])
from je_auto_control.utils.agent_runtime.errors import AgentTaskError  # noqa: E402
from je_auto_control.utils.agent_runtime.helper_owner_linux import (  # noqa: E402
    OwnerServiceChannel, SeqpacketTransport)

endpoint, mode = sys.argv[2], sys.argv[3]


def emit(value):
    print(json.dumps(value), flush=True)


def nested():
    """Policy 3 parent: ask it to open a child lease, then close the child, then itself."""
    parent = OwnerServiceChannel(SeqpacketTransport(endpoint), 3)
    for step, operation in (("nest", "nest"), ("close_child", "close")):
        try:
            emit({"stage": step, "result": parent.request(operation, {}, timeout=40)})
        except AgentTaskError as error:
            emit({"stage": step, "error": str(error)})
        sys.stdin.readline()
    try:
        parent.close()
        emit({"stage": "close", "retired": parent.retired})
    except AgentTaskError as error:
        emit({"stage": "close", "error": str(error), "retired": parent.retired})
    sys.exit(0)


def observe_later(channel):
    """After an unretired close: what the service reports for the record a moment later."""
    import time
    from je_auto_control.utils.agent_runtime import owner_service_wire as wire
    from je_auto_control.utils.agent_runtime.helper_owner_linux import _nonce
    if channel._ticket is None:
        return {"ticket": None}
    time.sleep(2)
    try:
        reply = channel._call(wire.ServiceRequest(wire.OP_OBSERVE, _nonce(), lease=channel._lease,
                                                  ticket=channel._ticket), time.monotonic() + 5)
        return {key: value for key, value in vars(reply).items() if key not in ("data",)}
    except (AgentTaskError, TimeoutError) as error:
        return {"failed": str(error)}


def race():
    """Close each lease the moment START is acknowledged, while launch may still run."""
    import time
    outcomes = []
    for _ in range(7):
        channel = OwnerServiceChannel(SeqpacketTransport(endpoint), 1)
        try:
            channel._ensure_started(time.monotonic() + 20)  # Lease and START only; no request.
            channel.close()
            outcomes.append({"retired": channel.retired})
        except AgentTaskError as error:
            outcomes.append({"error": str(error), "retired": channel.retired, "later": observe_later(channel)})
    emit({"stage": "race", "outcomes": outcomes})
    sys.exit(0)


def worker():
    """Policy 4, the package's real native worker: bootstrap through the service, then close."""
    channel = OwnerServiceChannel(SeqpacketTransport(endpoint), 4)
    try:
        emit({"stage": "bootstrap", "result": channel.request("bootstrap", {}, timeout=60)})
    except AgentTaskError as error:
        emit({"stage": "bootstrap", "error": str(error)})
    sys.stdin.readline()
    try:
        channel.close()
        emit({"stage": "close", "retired": channel.retired})
    except AgentTaskError as error:
        emit({"stage": "close", "error": str(error), "retired": channel.retired})
    sys.exit(0)


def remote():
    """Policy 5, a remote helper: the negotiation RemoteTarget performs, then close."""
    channel = OwnerServiceChannel(SeqpacketTransport(endpoint), 5)
    try:
        replies = [channel.request(operation, {}, timeout=60) for operation in ("bootstrap", "remote_capabilities")]
        emit({"stage": "negotiate", "replies": replies})
    except AgentTaskError as error:
        emit({"stage": "negotiate", "error": str(error)})
    sys.stdin.readline()
    try:
        channel.close()
        emit({"stage": "close", "retired": channel.retired})
    except AgentTaskError as error:
        emit({"stage": "close", "error": str(error), "retired": channel.retired})
    sys.exit(0)


if mode == "remote":
    remote()
if mode == "worker":
    worker()
if mode == "nested":
    nested()
if mode == "race":
    race()

try:
    channel = OwnerServiceChannel(SeqpacketTransport(endpoint), 1)
    reply = channel.request("ping", {}, timeout=20)
    escaped = channel.request("escape", {}, timeout=20) if mode == "hold" else None
except AgentTaskError as error:
    emit({"stage": "request", "error": str(error)})
    sys.exit(0 if mode == "foreign" else 1)
emit({"stage": "request", "reply": reply, "escaped": escaped})
if mode == "foreign":
    sys.exit(1)
for command in sys.stdin:
    command = command.strip()
    if command == "leftovers":
        emit({"stage": "leftovers", "reply": channel.request("leftovers", {}, timeout=20)})
    elif command == "umask":
        emit({"stage": "umask", "reply": channel.request("umask", {}, timeout=20)})
    elif command == "spawn":
        try:
            emit({"stage": "spawn", "reply": channel.request("spawn", {}, timeout=20)})
        except AgentTaskError as error:
            emit({"stage": "spawn", "error": str(error)})
    elif command == "ping":
        try:
            emit({"stage": "ping", "reply": channel.request("ping", {}, timeout=20)})
        except AgentTaskError as error:
            emit({"stage": "ping", "error": str(error)})
    elif command == "close":
        break
try:
    channel.close()
    emit({"stage": "close", "retired": channel.retired})
except AgentTaskError as error:
    emit({"stage": "close", "error": str(error), "retired": channel.retired})
