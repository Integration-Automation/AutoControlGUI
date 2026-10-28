"""Linux transport availability never widens shared-desktop presence or input gates."""
import sys

import pytest

from je_auto_control.utils.agent_runtime import activity, presence_host
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy
from je_auto_control.utils.agent_runtime.presence_channel_linux import LinuxChannel, LinuxListener


@pytest.mark.parametrize('platform', ['linux', 'darwin', 'freebsd'])
def test_transport_types_do_not_enable_non_windows_presence_or_input(monkeypatch, platform):
    assert LinuxChannel.connect and LinuxListener.create
    monkeypatch.setattr(sys, 'platform', platform)
    with pytest.raises(AgentControlBusy, match='Windows console session'):
        presence_host.require_windows()
    with pytest.raises(AgentControlBusy, match='trusted platform adapter'):
        activity.desktop_activity_gate(lambda: pytest.fail('takeover callback must remain inert'))
