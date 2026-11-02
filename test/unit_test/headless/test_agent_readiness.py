"""Readiness diagnostics stay passive, use one closed vocabulary and never claim native evidence."""
import json

import pytest

from je_auto_control.utils.agent_runtime import readiness
from je_auto_control.wrapper.capabilities import BackendContext, CapabilityStatus


def _report(platform='win32', environ=None, *, tools=(), packages=(), **context):
    found = set(tools)
    installed = set(packages)
    return readiness.agent_runtime_readiness(
        BackendContext(platform, environ or {}, **context),
        which=lambda name: f'/bin/{name}' if name in found else None,
        find_spec=lambda name: object() if name in installed else None)


def _area(report, name):
    return next(item for item in report['areas'] if item['area'] == name)


def test_every_area_uses_the_closed_vocabulary_and_records_no_native_evidence():
    for platform, environ in (('win32', {}), ('darwin', {}), ('linux', {'DISPLAY': ':0'}),
                              ('linux', {'WAYLAND_DISPLAY': 'wayland-0', 'XDG_SESSION_TYPE': 'wayland'}),
                              ('sunos5', {})):
        report = _report(platform, environ)
        assert report['passive'] is True
        assert report['states'] == list(readiness.STATES)
        assert {item['state'] for item in report['areas']} <= set(readiness.STATES)
        assert all(item['native_evidence'] == 'not_recorded' for item in report['areas'])
        assert 'measured' not in {item['state'] for item in report['areas']}
        json.dumps(report)


def test_missing_tools_and_packages_are_dependencies_and_present_ones_are_only_unprobed():
    absent = _report()
    assert _area(absent, 'android_transport')['state'] == 'missing_dependency'
    assert _area(absent, 'browser')['state'] == 'missing_dependency'
    present = _report(tools=('adb',), packages=('je_web_runner',))
    assert _area(present, 'android_transport')['state'] == 'not_probed'
    assert _area(present, 'browser')['state'] == 'not_probed'


def test_unimplemented_device_control_is_unsupported_even_when_its_tools_are_installed():
    report = _report(tools=('adb',))
    assert _area(report, 'android_managed_control')['state'] == 'unsupported'
    assert _area(report, 'ios_managed_control')['state'] == 'unsupported'


@pytest.mark.parametrize('platform,environ,state,backend', [
    ('win32', {}, 'not_probed', 'win32'),
    ('darwin', {}, 'not_probed', 'quartz'),
    ('linux', {'DISPLAY': ':0'}, 'not_probed', 'x11'),
    ('linux', {'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}, 'unsupported', 'unsupported'),
    ('freebsd14', {'DISPLAY': ':0'}, 'unsupported', 'unsupported'),
])
def test_only_a_platform_with_a_presence_source_reports_one(platform, environ, state, backend):
    area = _area(_report(platform, environ), 'presence_source')
    assert (area['state'], area['backend']) == (state, backend)
    if platform != 'win32':
        assert 'shared-desktop input stays refused' in area['detail']


@pytest.mark.parametrize('observed,state', [
    ('available', 'not_recorded'), ('needs_permission', 'unauthorized'), ('revoked', 'unauthorized'),
    ('needs_dependency', 'missing_dependency'), ('unverified', 'not_probed'), ('failed', 'not_probed'),
])
def test_a_local_capability_observation_maps_without_becoming_measured(observed, state):
    status = CapabilityStatus('input', observed, 'win32', 'observed locally', 'none', True)
    area = _area(_report(input_state=status), 'desktop_input')
    assert area['state'] == state
    assert area['observed'] == observed


def test_the_report_never_contacts_a_device_or_imports_the_browser_package():
    calls = []
    report = readiness.agent_runtime_readiness(
        BackendContext('win32', {}), which=lambda name: calls.append(('which', name)),
        find_spec=lambda name: calls.append(('find_spec', name)))
    assert sorted(calls) == [('find_spec', 'je_web_runner'), ('which', 'adb')]
    assert report['platform'] == 'win32'


def test_every_surface_reaches_the_same_report():
    import je_auto_control
    from je_auto_control.utils.agent_runtime import api, commands
    from je_auto_control.utils.rbac.policy import TOOL_CAPABILITIES
    assert je_auto_control.agent_runtime_readiness is api.agent_runtime_readiness
    assert commands.COMMANDS['AC_agent_runtime_readiness'] is api.agent_runtime_readiness
    assert 'ac_agent_runtime_readiness' in TOOL_CAPABILITIES
    assert set(api.agent_runtime_readiness()) == {'platform', 'display_server', 'passive', 'states', 'areas'}
