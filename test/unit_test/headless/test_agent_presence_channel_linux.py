"""Real subprocess channel factories, writer identity and resource retirement on Linux."""
from contextlib import contextmanager
from dataclasses import asdict, replace
import errno
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime import presence_channel_linux as module
from je_auto_control.utils.agent_runtime import presence_messages_linux as messages
from .presence_linux_test_support import native_support


BOOTSTRAP = '''
from dataclasses import asdict
import json,os,socket,struct,subprocess,sys
from je_auto_control.utils.agent_runtime.presence_channel_linux import LinuxChannel
from je_auto_control.utils.agent_runtime.presence_endpoint_linux import LinuxEndpoint,FileIdentity
from je_auto_control.utils.agent_runtime.presence_peer_linux import LinuxPeerIdentity
v=json.loads(sys.argv[1])
v['directory_identity']=FileIdentity(**v['directory_identity'])
v['socket_identity']=FileIdentity(**v['socket_identity'])
v['listener_process']=LinuxPeerIdentity(**v['listener_process'])
ch=LinuxChannel.connect(LinuxEndpoint(**v),timeout=1)
print('READY',flush=True)
'''


def descriptors():
    return {int(name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/' + name)}


def read_line(child):
    ready, _, _ = select.select([child.stdout], [], [], 5)
    if not ready:
        raise AssertionError('owned child output timed out')
    value = child.stdout.readline()
    if not value:
        raise AssertionError('owned child exited before output')
    return value.strip()


@contextmanager
def connected(body="ch.send({'hello': 1},timeout=1)"):
    with tempfile.TemporaryDirectory(prefix='ac-channel-') as runtime:
        listener = module.LinuxListener.create(runtime)
        child = subprocess.Popen([sys.executable, '-c', BOOTSTRAP + '\n' + body + '''
sys.stdin.buffer.read(1)
ch.close()
''', json.dumps(asdict(listener.endpoint))], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
        channel = None
        try:
            channel = listener.accept(timeout=1)
            if read_line(child) != b'READY':
                raise AssertionError('owned child factory did not complete')
            yield listener, channel, child
        finally:
            if child.poll() is None:
                child.stdin.write(b'Q')
                child.stdin.flush()
            try:
                output, errors = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=5)
                raise
            try:
                if channel is not None:
                    channel.close()
            finally:
                listener.close()
            if child.returncode or errors:
                raise AssertionError((child.returncode, output, errors))


@unittest.skipUnless(sys.platform == 'linux', 'native Linux channel factories required')
class ChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_support()

    def test_real_factory_roundtrip_noninheritability_and_no_leaks(self):
        before = descriptors()
        body = """
ch.send({'hello': 1},timeout=1)
reply=ch.receive(timeout=1)
print(json.dumps(reply),flush=True)
print(json.dumps([os.get_inheritable(ch._owner._state.resources.connection.fileno()),
 os.get_inheritable(ch._owner._state.resources.peer._descriptor)]),flush=True)
"""
        with connected(body) as (listener, channel, child):
            self.assertEqual(channel.receive(timeout=1), {'hello': 1})
            channel.send({'answer': 2}, timeout=1)
            self.assertEqual(json.loads(read_line(child)), {'answer': 2})
            self.assertEqual(json.loads(read_line(child)), [False, False])
            self.assertTrue(all(not os.get_inheritable(fd) for fd in descriptors() - before))
            self.assertEqual(Path(listener.endpoint.directory).stat().st_mode & 0o777, 0o700)
            self.assertEqual((Path(listener.endpoint.directory) / 'channel.sock').stat().st_mode & 0o777, 0o600)
        self.assertEqual(descriptors(), before)

    def test_listener_close_does_not_close_returned_channel(self):
        with connected() as (listener, channel, _child):
            listener.close()
            self.assertFalse(Path(listener.endpoint.directory).exists())
            self.assertEqual(channel.receive(timeout=1), {'hello': 1})

    def test_timeout_retires_channel(self):
        with connected('pass') as (_listener, channel, _child):
            start = time.monotonic()
            with self.assertRaisesRegex(AgentTaskError, 'timed out'):
                channel.receive(timeout=0.05)
            self.assertLess(time.monotonic() - start, 0.5)
            with self.assertRaisesRegex(AgentTaskError, 'retired'):
                channel.receive(timeout=1)

    def test_backpressured_send_consumes_one_deadline_and_retires(self):
        with connected('pass') as (_listener, channel, _child):
            channel._owner._state.resources.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            for _ in range(64):
                try:
                    channel.send({'body': 'x' * 3000}, timeout=0.05)
                except AgentTaskError as error:
                    self.assertIn('timed out', str(error))
                    break
            else:
                self.fail('owned socket send buffer did not apply backpressure')
            self.assertIsInstance(channel._owner._state, module._Retired)

    def test_concurrent_receivers_each_deliver_one_packet(self):
        results = []
        failures = []

        def receive(channel):
            try:
                results.append(channel.receive(timeout=1))
            except AgentTaskError as error:
                failures.append(str(error))

        body = "ch.send({'n':1},timeout=1); ch.send({'n':2},timeout=1)"
        with connected(body) as (_listener, channel, _child):
            threads = [threading.Thread(target=receive, args=(channel,)) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(3)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(failures, [])
            self.assertEqual(sorted(results, key=lambda item: item['n']), [{'n': 1}, {'n': 2}])

    def test_listener_close_revokes_waiting_accept_and_cleans_endpoint(self):
        results = []

        def accept(listener):
            try:
                listener.accept(timeout=1)
            except AgentTaskError as error:
                results.append(str(error))

        before = descriptors()
        with tempfile.TemporaryDirectory(prefix='ac-accept-') as runtime:
            listener = module.LinuxListener.create(runtime)
            thread = threading.Thread(target=accept, args=(listener,))
            thread.start()
            listener.close()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(results), 1)
            self.assertIn('retired', results[0])
            self.assertEqual(list(Path(runtime).iterdir()), [])
        self.assertEqual(descriptors(), before)

    def test_descendant_writer_refused_while_original_connector_lives(self):
        writer = "import socket,sys; s=socket.socket(fileno=int(sys.argv[1])); s.send(b'{}'); s.close()"
        body = f"""
s=ch._owner._state.resources.connection
child=subprocess.run([sys.executable,'-c',{writer!r},str(s.fileno())],pass_fds=(s.fileno(),),
 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
if child.returncode or child.stderr:
    raise RuntimeError(child.stderr)
"""
        with connected(body) as (_listener, channel, child):
            before = descriptors()
            with self.assertRaisesRegex(AgentTaskError, 'writer is not the live original'):
                channel.receive(timeout=1)
            self.assertIsNone(child.poll())
            self.assertEqual(len(before - descriptors()), 2)

    def test_rights_and_control_truncation_retire_actual_received_copies(self):
        for count in (1, 32):
            body = f"""
fds=[os.open('/dev/null',os.O_RDONLY) for _ in range({count})]
s=ch._owner._state.resources.connection
s.sendmsg([b'{{}}'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack('i'*len(fds),*fds))])
print(json.dumps([os.fstat(fd).st_mode for fd in fds]),flush=True)
for fd in fds:
    os.close(fd)
"""
            with self.subTest(count=count), connected(body) as (_listener, channel, child):
                before = descriptors()
                with self.assertRaises(AgentTaskError):
                    channel.receive(timeout=1)
                self.assertEqual(len(json.loads(read_line(child))), count)
                self.assertEqual(len(before - descriptors()), 2)

    def test_queued_cancellation_revokes_active_receive(self):
        cancel = threading.Event()
        results = []

        def receive(channel, cancellation):
            try:
                results.append(channel.receive(timeout=1, cancel=cancellation))
            except AgentTaskError as error:
                results.append(str(error))

        with connected('pass') as (_listener, channel, _child):
            first = threading.Thread(target=receive, args=(channel, None))
            second = threading.Thread(target=receive, args=(channel, cancel))
            first.start()
            deadline = time.monotonic() + 1
            while not channel._owner._state.active and time.monotonic() < deadline:
                threading.Event().wait(0.001)
            second.start()
            cancel.set()
            first.join(3)
            second.join(3)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertEqual(len(results), 2)
            self.assertTrue(any('cancelled' in result for result in results))
            self.assertTrue(any('retired' in result for result in results))

    def test_closed_descriptor_numbers_can_be_reused_without_repeat_close(self):
        with connected('pass') as (_listener, channel, _child):
            number = channel._owner._state.resources.connection.fileno()
            channel.close()
            opened = os.open('/dev/null', os.O_RDONLY)
            try:
                if opened != number:
                    os.dup2(opened, number, inheritable=False)
                channel.close()
                self.assertTrue(os.fstat(number))
            finally:
                os.close(opened)
                if opened != number:
                    os.close(number)

    def test_received_fd_close_failure_remains_unconfirmed_after_channel_resources_retire(self):
        with (
            tempfile.TemporaryDirectory(prefix='ac-close-failure-') as runtime,
            module.LinuxListener.create(runtime) as listener,
            module.LinuxChannel.connect(listener.endpoint, timeout=1) as client,
        ):
            channel = listener.accept(timeout=1)
            before = descriptors()
            reused = []
            real_close = os.close

            def close(descriptor):
                real_close(descriptor)
                if descriptor not in before:
                    reused.append(os.open('/dev/null', os.O_RDONLY))
                    raise OSError('owned receive descriptor close reported failure')

            try:
                client.send({'data': 1}, timeout=1)
                with patch.object(messages.os, 'close', side_effect=close):
                    with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                        channel.receive(timeout=1)
                for _ in range(2):
                    with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                        channel.close()
                self.assertTrue(channel._owner._state.unconfirmed)
                self.assertEqual(len(reused), 1)
                self.assertTrue(os.fstat(reused[0]))
            finally:
                for descriptor in reused:
                    real_close(descriptor)

    def test_cancel_after_receive_discards_packet(self):
        cancel = threading.Event()
        original = messages._snapshot

        def snapshot(*args):
            result = original(*args)
            cancel.set()
            return result

        with connected() as (_listener, channel, _child):
            before = descriptors()
            with patch.object(messages, '_snapshot', side_effect=snapshot):
                with self.assertRaisesRegex(AgentTaskError, 'cancelled'):
                    channel.receive(timeout=1, cancel=cancel)
            self.assertEqual(len(before - descriptors()), 2)

    def test_close_during_metadata_is_bounded_and_finalizer_discards(self):
        entered, release = threading.Event(), threading.Event()
        original = messages._snapshot
        results = []

        def snapshot(*args):
            entered.set()
            if not release.wait(3):
                raise AssertionError('owned metadata barrier not released')
            return original(*args)

        def receive(channel):
            try:
                results.append(channel.receive(timeout=1))
            except AgentTaskError as error:
                results.append(str(error))

        with connected() as (_listener, channel, _child):
            owned = {channel._owner._state.resources.connection.fileno(),
                     channel._owner._state.resources.peer._descriptor}
            with patch.object(messages, '_snapshot', side_effect=snapshot):
                thread = threading.Thread(target=receive, args=(channel,))
                thread.start()
                try:
                    self.assertTrue(entered.wait(1))
                    start = time.monotonic()
                    with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                        channel.close(timeout=0.05)
                    self.assertLess(time.monotonic() - start, 0.5)
                    self.assertTrue(owned <= descriptors())
                finally:
                    release.set()
                    thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(results), 1)
            self.assertIn('retired', results[0])
            self.assertFalse(owned & descriptors())
            channel.close()

    def test_finite_json_failure_retires_received_pidfd(self):
        for raw in (b'', b'{"a":1,"a":2}', b'{"x":NaN}', b'[]', b'x' * 4097, b'x' * 8192):
            with self.subTest(raw=raw[:32]), connected(
                    f'ch._owner._state.resources.connection.send({raw!r})') as (_listener, channel, _child):
                before = descriptors()
                with self.assertRaises(AgentTaskError):
                    channel.receive(timeout=1)
                self.assertEqual(len(before - descriptors()), 2)

    def test_trusted_listener_identity_cannot_be_replaced_by_path_metadata(self):
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            with module.LinuxListener.create(runtime) as listener:
                wrong = replace(listener.endpoint,
                                listener_process=replace(listener.endpoint.listener_process, birth=1))
                before = descriptors()
                with self.assertRaises(AgentTaskError):
                    module.LinuxChannel.connect(wrong, timeout=1)
                self.assertEqual(descriptors(), before)

    def test_real_negative_emfile_pidfd_in_disposable_receiver(self):
        body = """
import errno,resource,select
from unittest.mock import patch
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_peer_linux import _socket_constant
soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE,(min(64,hard),hard))
filled=[]
try:
    while True:
        try:
            filled.append(os.open('/dev/null',os.O_RDONLY))
        except OSError as error:
            if error.errno!=errno.EMFILE:
                raise
            break
    print('EXHAUSTED',flush=True)
    s=ch._owner._state.resources.connection
    if not select.select([s],[],[],3)[0]:
        raise RuntimeError('first owned packet did not arrive')
    raw,anc,flags,_=s.recvmsg(4097,socket.CMSG_SPACE(12)+socket.CMSG_SPACE(4),socket.MSG_CMSG_CLOEXEC)
    values=[struct.unpack('i',v)[0] for level,kind,v in anc if kind==_socket_constant('SCM_PIDFD')]
    print(json.dumps({'values':values,'truncated':bool(flags&socket.MSG_CTRUNC)}),flush=True)
    if values!=[-errno.EMFILE] or flags&socket.MSG_CTRUNC:
        raise RuntimeError('kernel did not reproduce the negative pidfd condition')
    original_close=os.close
    def close(fd):
        if fd<0:
            raise AssertionError('negative close forbidden')
        original_close(fd)
    with patch.object(os,'close',side_effect=close),patch.object(os,'pidfd_open',
            side_effect=AssertionError('PID reopen forbidden')):
        try:
            ch.receive(timeout=1)
        except AgentTaskError as error:
            print(str(error),flush=True)
        else:
            raise RuntimeError('negative sender pidfd was accepted')
finally:
    for fd in filled:
        os.close(fd)
    resource.setrlimit(resource.RLIMIT_NOFILE,(soft,hard))
"""
        with connected(body) as (_listener, channel, child):
            self.assertEqual(read_line(child), b'EXHAUSTED')
            channel.send({'packet': 1}, timeout=1)
            channel.send({'packet': 2}, timeout=1)
            self.assertEqual(json.loads(read_line(child)), {'values': [-errno.EMFILE], 'truncated': False})
            self.assertIn(b'sender pidfd or credentials are unavailable', read_line(child))


class ChannelBoundaryTests(unittest.TestCase):
    def test_direct_constructors_and_non_linux_factories_refuse(self):
        with self.assertRaises(AgentTaskError):
            module.LinuxChannel()
        with self.assertRaises(AgentTaskError):
            module.LinuxListener()
        with patch.object(module.sys, 'platform', 'win32'):
            with self.assertRaises(AgentTaskError):
                module.LinuxListener.create('/unused')
            with self.assertRaises(AgentTaskError):
                module.LinuxChannel.connect(None, timeout=1)

    def test_timeout_boundary_is_finite_positive_and_bounded(self):
        for value in (True, False, None, 0, -1, 1.001, float('inf'), float('nan'), '1'):
            with self.subTest(value=value), self.assertRaises(AgentTaskError):
                module._deadline(value)
