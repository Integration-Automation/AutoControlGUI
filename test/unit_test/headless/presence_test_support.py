"""Explicit virtual presence source for unit and owned-process tests; never uses native observation."""
import threading

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_state import PresenceState


class Source:
    def __init__(self, events=None):
        self.events, self.now = events if events is not None else [], 0.0
        self.state = PresenceState(lambda: self.now)
        self.released = threading.Event()
        self.fail_start = False

    def start(self):
        self.events.append('start')
        if self.fail_start:
            raise AgentTaskError('source start refused')
        self.state.refresh(True, False)

    def advance(self, seconds):
        for _step in range(int(seconds * 8)):
            self.now += 0.125
            self.state.refresh(True, False)

    def status(self):
        return self.state.inspect()

    def request(self, operation, body):
        self.state.refresh(True, False)
        methods = {'inspect': self.state.inspect, 'acquire': self.state.acquire, 'check': self.state.check}
        return methods[operation](**body)

    def release(self, **body):
        self.state.release(**body)
        self.released.set()

    def close(self):
        self.events.append('source-close')
        self.state.close()
