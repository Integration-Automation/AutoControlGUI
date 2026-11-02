"""Protected acceptance remote helper: the host-side entry a deployment writes around
``serve_remote_worker``, with an adapter that reaches no device.

Usage: python3 -I -B remote_helper.py <repository root>
It proves the remote worker's process model under the owner service (payload ID, empty
environment, identity filter, negotiation through the relay). Talking to a real device is
the deferred real-device acceptance.
"""
import sys

sys.path.insert(0, sys.argv[1])
from je_auto_control.utils.agent_runtime.errors import AgentTaskError  # noqa: E402
from je_auto_control.utils.agent_runtime.remote_worker import serve_remote_worker  # noqa: E402


class NoDevice:
    """Accepts the takeover hook; any device operation is refused."""

    def set_takeover_handler(self, handler):
        self.handler = handler

    def __getattr__(self, name):
        def refuse(*_args, **_kwargs):
            raise AgentTaskError(f"no device behind this acceptance helper ({name})")
        return refuse


serve_remote_worker(NoDevice)
