"""Independent GDBus GlobalShortcuts peer on a private verification bus.

Wire contract: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html
This service creates no desktop binding or consent dialog.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from gi.repository import Gio, GLib  # pylint: disable=import-error  # System GI exists only in the Linux peer image/job.

from portal_server import REQUEST_XML, SESSION_XML, sender_token

_BUS = 'org.freedesktop.portal.Desktop'
_PATH = '/org/freedesktop/portal/desktop'
_INTERFACE = 'org.freedesktop.portal.GlobalShortcuts'
_CONTROL = 'org.autocontrol.Verify'
_TRIGGER = 'Ctrl+Shift+F7 (test portal)'
_XML = """<node>
<interface name='org.freedesktop.portal.GlobalShortcuts'>
 <method name='CreateSession'><arg type='a{sv}' direction='in'/><arg type='o' direction='out'/></method>
 <method name='BindShortcuts'>
  <arg type='o' direction='in'/><arg type='a(sa{sv})' direction='in'/>
  <arg type='s' direction='in'/><arg type='a{sv}' direction='in'/><arg type='o' direction='out'/>
 </method>
 <signal name='Activated'><arg type='o'/><arg type='s'/><arg type='t'/><arg type='a{sv}'/></signal>
 <signal name='Deactivated'><arg type='o'/><arg type='s'/><arg type='t'/><arg type='a{sv}'/></signal>
</interface>
<interface name='org.autocontrol.Verify'>
 <method name='Emit'><arg type='o' direction='in'/><arg type='s' direction='in'/><arg type='s' direction='in'/></method>
 <method name='Revoke'><arg type='o' direction='in'/></method>
 <method name='DropName'/>
</interface>
</node>"""


class ShortcutPortal:  # pylint: disable=too-few-public-methods  # One owned service with run as its sole entry point.
    """Record actual wire requests and direct signals to each requesting connection."""

    def __init__(self, record: Path, behaviour: str) -> None:
        self.path = record
        self.behaviour = behaviour
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sessions: dict[str, str] = {}
        self.exports: list[int] = []
        self.record = {'ready': False, 'creates': [], 'binds': [], 'sessions_closed': [], 'requests_closed': []}

    def _flush(self) -> None:
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.record), encoding='utf-8')
        temporary.replace(self.path)

    def _export(self, path: str, xml: str) -> None:
        for info in Gio.DBusNodeInfo.new_for_xml(xml).interfaces:
            self.exports.append(self.bus.register_object(path, info, self._call, None, None))

    def run(self) -> None:
        """Serve one scenario until the verifier terminates this owned child."""
        self._export(_PATH, _XML)
        Gio.bus_own_name_on_connection(self.bus, _BUS, Gio.BusNameOwnerFlags.NONE, self._owned, None)
        GLib.MainLoop().run()

    def _owned(self, *_args) -> None:
        self.record['ready'] = True
        self._flush()

    def _call(self, *args) -> None:
        _connection, sender, path, interface, method, parameters, invocation = args
        values = parameters.unpack()
        if interface == 'org.freedesktop.portal.Request':
            self.record['requests_closed'].append(path)
        elif interface == 'org.freedesktop.portal.Session':
            self.record['sessions_closed'].append(path)
        elif method == 'CreateSession':
            self._create(sender, values[0], invocation)
            return
        elif method == 'BindShortcuts':
            self._bind(sender, values, invocation)
            return
        elif method == 'Emit':
            self._emit(*values)
        elif method == 'Revoke':
            session = values[0]
            self.bus.emit_signal(self.sessions[session], session, 'org.freedesktop.portal.Session',
                                 'Closed', GLib.Variant('(a{sv})', ({},)))
        elif method == 'DropName':
            invocation.return_value(None)
            self.bus.flush_sync(None)
            self.bus.close_sync(None)
            return
        else:
            invocation.return_dbus_error('org.autocontrol.Verify.UnknownMethod', method)
            return
        self._flush()
        invocation.return_value(None)

    def _request(self, sender: str, options: dict) -> str:
        request = f"{_PATH}/request/{sender_token(sender)}/{options['handle_token']}"
        self._export(request, REQUEST_XML)
        return request

    def _create(self, sender: str, options: dict, invocation) -> None:
        request = self._request(sender, options)
        session = f"{_PATH}/session/{sender_token(sender)}/{options['session_handle_token']}"
        self.sessions[session] = sender
        self.record['creates'].append({'session': session, 'sender': sender})
        self._export(session, SESSION_XML)
        self._flush()
        invocation.return_value(GLib.Variant('(o)', (request,)))
        GLib.idle_add(self._response, sender, request, 0, {'session_handle': GLib.Variant('s', session)})

    def _bind(self, sender: str, values: tuple, invocation) -> None:
        session, shortcuts, parent, options = values
        request = self._request(sender, options)
        self.record['binds'].append({'session': session, 'shortcuts': shortcuts, 'parent': parent})
        self._flush()
        invocation.return_value(GLib.Variant('(o)', (request,)))
        if self.behaviour == 'stall':
            return
        if self.behaviour == 'early':
            for member in ('Activated', 'Activated', 'Deactivated', 'Activated'):
                self._emit(session, 'autocontrol-stop', member)
        denied = self.behaviour == 'deny'
        result = {} if denied else {'shortcuts': GLib.Variant(
            'a(sa{sv})', [('autocontrol-stop', {'trigger_description': GLib.Variant('s', _TRIGGER)})])}
        GLib.idle_add(self._response, sender, request, 1 if denied else 0, result)

    def _response(self, sender: str, request: str, code: int, result: dict) -> bool:
        self.bus.emit_signal(sender, request, 'org.freedesktop.portal.Request', 'Response',
                             GLib.Variant('(ua{sv})', (code, result)))
        return False

    def _emit(self, session: str, identifier: str, member: str) -> None:
        if member not in ('Activated', 'Deactivated'):
            raise ValueError('invalid verification signal')
        self.bus.emit_signal(self.sessions[session], _PATH, _INTERFACE, member,
                             GLib.Variant('(osta{sv})', (session, identifier, time.monotonic_ns() // 1_000_000, {})))


def main() -> None:
    """Use Debian's GI interpreter; the client uses the separately installed wheel."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--behaviour', choices=('grant', 'deny', 'stall', 'early'), default='grant')
    args = parser.parse_args()
    ShortcutPortal(args.record, args.behaviour).run()


if __name__ == '__main__':
    main()
