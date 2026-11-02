"""Each platform gets its own trusted presence source, and one without such a source refuses."""
import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_platform import default_presence_api, presence_backend
from je_auto_control.utils.agent_runtime.presence_quartz import QuartzPresenceAPI
from je_auto_control.utils.agent_runtime.presence_win32 import Win32PresenceAPI
from je_auto_control.utils.agent_runtime.presence_x11 import X11PresenceAPI


@pytest.mark.parametrize('platform,environ,backend', [
    ('win32', {}, 'win32'),
    ('darwin', {}, 'quartz'),
    ('linux', {'DISPLAY': ':0'}, 'x11'),
    ('linux', {'DISPLAY': ':0', 'XDG_SESSION_TYPE': 'x11'}, 'x11'),
    ('linux', {'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}, 'unsupported'),
    ('linux', {'DISPLAY': ':1', 'XDG_SESSION_TYPE': 'wayland'}, 'unsupported'),
    ('linux', {}, 'unsupported'),
    ('freebsd14', {'DISPLAY': ':0'}, 'unsupported'),
    ('cygwin', {}, 'unsupported'),
])
def test_the_backend_follows_platform_and_display_server(platform, environ, backend):
    assert presence_backend(platform, environ) == backend


@pytest.mark.parametrize('platform,environ,kind', [
    ('win32', {}, Win32PresenceAPI), ('darwin', {}, QuartzPresenceAPI), ('linux', {'DISPLAY': ':0'}, X11PresenceAPI),
])
def test_construction_is_inert_and_picks_the_platform_api(platform, environ, kind, monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_x11
    monkeypatch.setattr(presence_x11.shutil, 'which', lambda _name: None)
    assert isinstance(default_presence_api(platform, environ), kind)


def test_a_platform_without_a_trusted_source_refuses():
    with pytest.raises(AgentTaskError, match='no trusted physical presence source'):
        default_presence_api('linux', {'WAYLAND_DISPLAY': 'wayland-0'})
