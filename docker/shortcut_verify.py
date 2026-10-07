"""Verify an installed wheel's stop sessions against independent GDBus on a real private bus.

Run with dbus-run-session. This verifies wire transport, not a desktop consent UI
or physical keyboard-state recovery. Artifacts survive both success and failure.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import subprocess  # nosec B404  # reason: owned verification peer with explicit argv, never a shell.
import sys
import tempfile
import threading
import time
import traceback

import je_auto_control
from je_auto_control.linux_wayland._dbus_client import SessionBus
from je_auto_control.linux_wayland.global_shortcuts import ShortcutUnavailable, StopShortcutSession

_PATH = '/org/freedesktop/portal/desktop'
_BUS = 'org.freedesktop.portal.Desktop'
_CONTROL = 'org.autocontrol.Verify'


def wait_for(predicate, description: str, seconds: float = 5) -> None:
    """Keep every wire scenario bounded, including a missing peer."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError('timed out: ' + description)


class Peer:
    """Own one GI process and retain its protocol transcript outside its lifetime."""

    def __init__(self, output: Path, name: str, behaviour: str = 'grant') -> None:
        self.folder = output / name
        self.folder.mkdir(parents=True, exist_ok=True)
        self.record_path = self.folder / 'record.json'
        self.record_path.unlink(missing_ok=True)
        self.behaviour = behaviour
        self.process = None
        self.log = None
        self.bus = SessionBus()

    def __enter__(self):
        self.log = (self.folder / 'peer.log').open('wb')
        server = Path(__file__).with_name('shortcut_server.py')
        try:
            self.process = subprocess.Popen(  # nosec B603  # reason: fixed system GI interpreter and owned peer path.
                ['/usr/bin/python3', str(server), '--record', str(self.record_path),
                 '--behaviour', self.behaviour], stdout=self.log, stderr=subprocess.STDOUT)
            wait_for(self._ready, 'portal bus name')
            self.bus.connect()
            return self
        except BaseException:  # reason: failed startup must reclaim the same owned child and transcript.
            self.__exit__()
            raise

    def _ready(self) -> bool:
        if self.process.poll() is not None:
            raise RuntimeError('GI peer exited before acquiring the bus name; inspect peer.log')
        return self.record().get('ready', False)

    def record(self) -> dict:
        """Read only the bounded atomic record written by the independent peer."""
        try:
            with self.record_path.open('rb') as handle:
                payload = handle.read(65537)
        except FileNotFoundError:
            return {}
        if len(payload) > 65536:
            raise ValueError('verification record exceeded 64 KiB')
        return json.loads(payload)

    def control(self, member: str, signature: str = '', body=None) -> None:
        """Use a separate real connection for the test service's event controls."""
        self.bus.call(_BUS, _PATH, _CONTROL, member, signature, [] if body is None else body, timeout=3)

    def __exit__(self, *_args) -> None:
        self.bus.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.log is not None:
            self.log.close()


@contextmanager
def registration(on_stop):
    """Keep each application's grant paired with cleanup, including failed assertions."""
    owner = StopShortcutSession()
    owner.start(on_stop, preferred_trigger='F7')
    try:
        yield owner
    finally:
        owner.close()


def grant_and_isolation(output: Path) -> None:
    """Check actual binding, directed signal filtering, debounce and independent release."""
    with Peer(output, 'grant_and_isolation') as peer:
        first, second = [], []
        with registration(lambda: first.append(True)) as left:
            assert left.wait_ready(5)
            with registration(lambda: second.append(True)) as right:
                assert right.wait_ready(5)
                assert left.trigger_description == 'Ctrl+Shift+F7 (test portal)'
                records = peer.record()
                sessions = [entry['session'] for entry in records['creates']]
                assert len(set(sessions)) == 2 and len({entry['sender'] for entry in records['creates']}) == 2
                assert all(entry['shortcuts'][0][1]['preferred_trigger'] == 'F7' for entry in records['binds'])
                peer.control('Emit', 'oss', [sessions[1], 'foreign-stop', 'Activated'])
                peer.control('Emit', 'oss', [sessions[1], 'autocontrol-stop', 'Activated'])
                peer.control('Emit', 'oss', [sessions[1], 'autocontrol-stop', 'Activated'])
                wait_for(lambda: len(second) == 1, 'one held activation')
                assert not first
                left.close()
                wait_for(lambda: sessions[0] in peer.record()['sessions_closed'], 'first session Close')
                assert sessions[1] not in peer.record()['sessions_closed'] and right.state == 'available'
                peer.control('Emit', 'oss', [sessions[1], 'autocontrol-stop', 'Deactivated'])
                peer.control('Emit', 'oss', [sessions[1], 'autocontrol-stop', 'Activated'])
                wait_for(lambda: len(second) == 2, 'independent surviving owner')
        wait_for(lambda: set(sessions) <= set(peer.record()['sessions_closed']), 'both explicit session closes')
        assert not first and second == [True, True]


def early_activation(output: Path) -> None:
    """Signals delivered before Bind's Response must survive the method-reply queue."""
    with Peer(output, 'early_activation', 'early'):
        fired = []
        with registration(lambda: fired.append(True)) as owner:
            assert owner.wait_ready(5)
            wait_for(lambda: len(fired) == 2, 'ordered early activation/deactivation')


def denied_and_cancelled(output: Path) -> None:
    """Retain refusal without reauthorization and cancel an unanswered native request."""
    with Peer(output, 'denied', 'deny') as peer, registration(lambda: None) as owner:
        try:
            owner.wait_ready(5)
        except ShortcutUnavailable as error:
            assert error.state == 'needs_permission'
        else:
            raise AssertionError('denied shortcut became available')
        try:
            owner.start(lambda: None)
        except ShortcutUnavailable:
            pass
        else:
            raise AssertionError('cached refusal was automatically retried')
        assert len(peer.record()['creates']) == 1
    with Peer(output, 'cancelled', 'stall') as peer, registration(lambda: None) as owner:
        wait_for(lambda: bool(peer.record().get('binds')), 'pending Bind request')
        started = time.monotonic()
        owner.close()
        assert time.monotonic() - started < 3 and owner.state == 'closed'
        wait_for(lambda: bool(peer.record()['requests_closed']), 'pending Request Close')
        assert len(peer.record()['sessions_closed']) == 1


def revoked(output: Path) -> None:
    """A native Session::Closed invokes cancellation and revokes local availability."""
    with Peer(output, 'revoked') as peer:
        stopped = threading.Event()
        with registration(stopped.set) as owner:
            assert owner.wait_ready(5)
            session = peer.record()['creates'][0]['session']
            peer.control('Revoke', 'o', [session])
            assert stopped.wait(3)
            assert owner.state == 'needs_permission'


def name_lost(output: Path, pending: bool = False) -> None:
    """Losing the well-known owner invalidates grants without killing the private bus."""
    with Peer(output, 'pending_name_lost' if pending else 'name_lost', 'stall' if pending else 'grant') as peer:
        stopped = threading.Event()
        with registration(stopped.set) as owner:
            wait_for(lambda: bool(peer.record().get('binds')), 'Bind before name loss')
            if not pending:
                assert owner.wait_ready(5)
            peer.control('DropName')
            wait_for(lambda: owner.state == 'needs_permission' and owner.error is not None, 'portal owner revocation')
            assert 'revoked' in owner.error.reason
            assert stopped.is_set() is not pending


def main() -> int:
    """Collect independent wire checks, preserving all failures and package identity."""
    if not __debug__:
        raise RuntimeError('verification assertions require an unoptimized interpreter')
    configured = os.environ.get('AC_SHORTCUT_ARTIFACT_DIR')
    output = Path(configured if configured else tempfile.mkdtemp(prefix='ac-shortcut-native-')).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = str(Path(je_auto_control.__file__).resolve())
    if 'site-packages' not in Path(package).parts:
        raise RuntimeError('native verification must exercise an installed wheel, not source/editable imports')
    results = {}
    checks = [('grant_and_isolation', grant_and_isolation), ('early_activation', early_activation),
              ('denied_and_cancelled', denied_and_cancelled), ('revoked', revoked), ('name_lost', name_lost),
              ('pending_name_lost', lambda folder: name_lost(folder, True))]
    for name, check in checks:
        try:
            check(output)
        # pylint: disable-next=broad-exception-caught  # Each failure remains in the transcript and nonzero result.
        except Exception:  # reason: collect each failed native check with traceback; never report it as success.
            traceback.print_exc()
            results[name] = False
        else:
            results[name] = True
        print(f'{name}: {"PASS" if results[name] else "FAIL"}', flush=True)
    (output / 'summary.json').write_text(json.dumps(
        {'python': sys.version, 'platform': platform.platform(), 'package': package, 'checks': results}, indent=2),
        encoding='utf-8')
    return sum(not passed for passed in results.values())


if __name__ == '__main__':
    raise SystemExit(main())
