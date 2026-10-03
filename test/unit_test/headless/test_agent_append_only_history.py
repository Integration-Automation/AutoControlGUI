"""Provider request histories stay immutable across screenshot compaction."""
import copy
import io
from types import SimpleNamespace

from PIL import Image
import pytest

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends import base
from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
from je_auto_control.utils.agent.backends.anthropic_computer_use import ComputerUseAgentBackend


def _png():
    buffer = io.BytesIO()
    Image.new('RGB', (20, 10), 'blue').save(buffer, format='PNG')
    return buffer.getvalue()


class RecordingClient:
    def __init__(self, kind):
        self.kind = kind
        self.calls = []
        self.snapshots = []
        self.messages = SimpleNamespace(create=self.create)
        self.beta = SimpleNamespace(messages=self.messages)

    def create(self, **request):
        self.calls.append(request)
        self.snapshots.append(copy.deepcopy(request))
        identifier = f'tool-{len(self.calls)}'
        name = {'generic': 'AC_screenshot', 'beta': 'computer', 'toolset': 'screenshot'}[self.kind]
        block = {'type': 'tool_use', 'id': identifier, 'name': name,
                 'input': {'action': 'screenshot'} if self.kind == 'beta' else {}}
        if self.kind == 'toolset':
            block['toolset_name'] = 'computer'
        thinking = SimpleNamespace(type='thinking', thinking='opaque reasoning', signature='bound signature')
        return SimpleNamespace(content=[thinking, block], stop_reason='tool_use')


def _backend(kind, client):
    if kind == 'generic':
        return AnthropicAgentBackend(client=client, tools=[{'name': 'AC_screenshot'}])
    kwargs = {'tool_type': 'computer_toolset_20260801'} if kind == 'toolset' else {}
    return ComputerUseAgentBackend(client=client, display_width_px=20, display_height_px=10, **kwargs)


def _run_turns(kind, turns):
    client = RecordingClient(kind)
    backend = _backend(kind, client)
    history = []
    for index in range(turns):
        backend.decide_next_action('Find the blue window', _png(), history)
        history.append(AgentStep(index, 'AC_screenshot', {}, result=f'captured frame {index}'))
    return client


@pytest.mark.parametrize('kind', ['generic', 'beta', 'toolset'])
def test_sent_turns_are_never_mutated(kind):
    client = _run_turns(kind, base.SCREENSHOTS_KEPT + 3)
    assert client.calls == client.snapshots


@pytest.mark.parametrize('kind', ['generic', 'beta', 'toolset'])
def test_compaction_opens_new_history(kind):
    client = _run_turns(kind, base.SCREENSHOTS_KEPT + 1)
    messages = client.snapshots[-1]['messages']
    assert len(messages) == 1
    assert messages[0]['role'] == 'user'
    assert 'Find the blue window' in messages[0]['content'][0]['text']
    assert 'AC_screenshot' in messages[0]['content'][0]['text']
    assert 'captured frame 2' in messages[0]['content'][0]['text']
    assert messages[0]['content'][-1]['type'] == 'image'
    assert 'tool_result' not in str(messages)
    assert 'bound signature' not in str(messages)


def test_compact_history_does_not_share_screenshot_blocks():
    messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'old'}]}]
    screenshot = {'type': 'image', 'source': {'type': 'base64', 'data': 'original'}}
    result = base.compact_history(messages, 'Goal: open window\nActions: click', screenshot)
    result[0]['content'][-1]['source']['data'] = 'changed'
    assert screenshot['source']['data'] == 'original'
    assert messages[0]['content'][0]['text'] == 'old'


def test_default_agent_tools_are_unchanged(monkeypatch):
    from je_auto_control.utils.agent import backends, agent_loop
    from je_auto_control.utils.executor.action_executor import _run_agent
    from je_auto_control.utils.tool_use_schema import export_anthropic_tools
    offered = []
    class Backend(agent_loop.FakeAgentBackend):
        def __init__(self, *, tools, **kwargs):
            offered.extend(tools)
            super().__init__([{'stop': True, 'message': 'done'}])
    monkeypatch.setattr(backends, 'AnthropicAgentBackend', Backend)
    monkeypatch.setattr(agent_loop, '_default_screenshot', lambda: None)
    assert _run_agent('goal')['succeeded'] is True
    assert offered == export_anthropic_tools()
    assert any(tool['name'] == 'AC_shell_command' for tool in offered)
