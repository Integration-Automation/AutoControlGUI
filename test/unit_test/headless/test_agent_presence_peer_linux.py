"""Actual Linux connected-process evidence, without desktop or application authority."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime import presence_peer_linux as module


@contextmanager
def connected(*, unusual_name=False, forward_writer=False, kind=socket.SOCK_STREAM):
    script = '''
import ctypes,os,socket,subprocess,sys
if sys.argv[2]=='1':
    ctypes.CDLL(None).prctl(15,b'peer ) 123 ( hi',0,0,0)
s=socket.socket(socket.AF_UNIX,int(sys.argv[4]))
s.connect(sys.argv[1])
if sys.argv[3]=='1':
    reader,writer=os.pipe()
    code=("import os,socket,sys; s=socket.socket(fileno=int(sys.argv[1])); "
          "os.read(int(sys.argv[2]),1); os.close(int(sys.argv[2])); "
          "s.sendall(b'G'); s.recv(1); s.sendall(b'A'); s.close()")
    grandchild=subprocess.Popen([sys.executable,'-c',code,str(s.fileno()),str(reader)],
        pass_fds=(s.fileno(),reader),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    os.close(reader)
    print(grandchild.pid,flush=True)
s.sendall(b'R')
sys.stdin.buffer.read(1)
if sys.argv[3]=='1':
    os.write(writer,b'G')
    os.close(writer)
s.close()
if sys.argv[3]=='1':
    os._exit(0)
'''
    with tempfile.TemporaryDirectory(prefix='autocontrol-peer-candidate-') as base:
        with socket.socket(socket.AF_UNIX, kind) as listener:
            address = str(Path(base) / 'owned.sock')
            listener.bind(address)
            listener.listen(1)
            listener.settimeout(5)
            child = subprocess.Popen([sys.executable, '-c', script, address,
                str(int(unusual_name)), str(int(forward_writer)), str(int(kind))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            connection = None
            descendant = None
            try:
                connection, _ = listener.accept()
                connection.settimeout(5)
                if connection.recv(1) != b'R':
                    raise RuntimeError('owned child did not become ready')
                if forward_writer:
                    descendant = os.pidfd_open(int(child.stdout.readline()))
                yield connection, child
            finally:
                finish_child(connection, child, descendant)


def finish_descendant(connection, descriptor):
    if descriptor is None:
        return
    try:
        connection.sendall(b'Q')
    except OSError:
        pass
    poll = select.poll()
    poll.register(descriptor, select.POLLIN)
    exited = poll.poll(5000)
    os.close(descriptor)
    if not exited:
        raise RuntimeError('owned descendant has not retired')


def finish_child(connection, child, descendant):
    if child.stdin is not None and not child.stdin.closed:
        child.stdin.close()
    code = child.wait(timeout=5)
    finish_descendant(connection, descendant)
    output, errors = child.stdout.read(), child.stderr.read()
    child.stdout.close()
    child.stderr.close()
    if connection is not None:
        connection.close()
    if code or output or errors:
        raise RuntimeError((code, output, errors))


def descriptors():
    return {name for name in os.listdir('/proc/self/fd')
            if os.path.exists('/proc/self/fd/' + name)}


@unittest.skipUnless(sys.platform == 'linux', 'native connected-process pidfd evidence is Linux-only')
class ConnectedPeerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            option = module._peer_option()
        except AgentTaskError as error:
            raise unittest.SkipTest('native pidfd socket option ABI is unavailable') from error
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with left, right:
            try:
                descriptor = left.getsockopt(socket.SOL_SOCKET, option)
            except OSError as error:
                if error.errno in {errno.ENOPROTOOPT, errno.EOPNOTSUPP, errno.ENOSYS}:
                    raise unittest.SkipTest('kernel has no connected-peer pidfd socket option') from error
                raise
            os.close(descriptor)

    def test_stream_and_seqpacket_factories_pin_actual_subprocess(self):
        for kind in (socket.SOCK_STREAM, socket.SOCK_SEQPACKET):
            with self.subTest(kind=kind), connected(kind=kind) as (connection, child):
                before = descriptors()
                peer = module.retain_connected_peer(connection)
                try:
                    self.assertEqual(peer.identity.pid, child.pid)
                    self.assertTrue(peer.alive())
                    self.assertFalse(os.get_inheritable(peer._descriptor))
                finally:
                    peer.close()
                self.assertEqual(descriptors(), before)

    def test_real_connected_child_has_kernel_identity_and_retained_liveness(self):
        with connected() as (connection, child):
            before = descriptors()
            peer = module.retain_connected_peer(connection)
            try:
                owned = descriptors() - before
                self.assertEqual(len(owned), 1)
                self.assertFalse(os.get_inheritable(int(owned.pop())))
                self.assertEqual(peer.identity.pid, child.pid)
                self.assertEqual((peer.identity.uid, peer.identity.gid), (os.geteuid(), os.getegid()))
                self.assertGreater(peer.identity.birth, 0)
                self.assertTrue(peer.alive())
                self.assertIsNone(child.poll())
            finally:
                peer.close()

    def test_process_comm_parentheses_cannot_change_birth_or_pid_parsing(self):
        with connected(unusual_name=True) as (connection, child):
            peer = module.retain_connected_peer(connection)
            try:
                self.assertEqual(peer.identity.pid, child.pid)
                self.assertTrue(peer.alive())
            finally:
                peer.close()

    def test_dead_original_is_refused_despite_stale_socket_credentials(self):
        with connected() as (connection, child):
            peer = module.retain_connected_peer(connection)
            try:
                child.stdin.close()
                self.assertEqual(child.wait(timeout=5), 0)
                self.assertEqual(struct.unpack('3i', connection.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0], child.pid)
                self.assertFalse(peer.alive())
                with patch.object(os, 'pidfd_open') as reopen:
                    with self.assertRaises(AgentTaskError):
                        module.retain_connected_peer(connection)
                    reopen.assert_not_called()
            finally:
                peer.close()

    def test_close_is_idempotent_and_does_not_stop_child_or_close_transport(self):
        with connected() as (connection, child):
            before = descriptors()
            peer = module.retain_connected_peer(connection)
            peer.close()
            peer.close()
            self.assertFalse(peer.alive())
            self.assertIsNone(child.poll())
            self.assertEqual(connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE), socket.SOCK_STREAM)
            self.assertEqual(descriptors(), before)

    def test_forwarded_socket_cannot_revive_the_retired_original_connector(self):
        with connected(forward_writer=True) as (connection, child):
            peer = module.retain_connected_peer(connection)
            try:
                child.stdin.close()
                self.assertEqual(child.wait(timeout=5), 0)
                self.assertEqual(connection.recv(1), b'G')
                self.assertFalse(peer.alive())
                with self.assertRaises(AgentTaskError):
                    module.retain_connected_peer(connection)
                connection.sendall(b'Q')
                self.assertEqual(connection.recv(1), b'A')
            finally:
                peer.close()

    def test_distinct_retained_handles_have_independent_ownership(self):
        with connected() as (connection, _):
            first = module.retain_connected_peer(connection)
            second = module.retain_connected_peer(connection)
            try:
                first.close()
                self.assertTrue(second.alive())
                self.assertFalse(first.alive())
            finally:
                first.close()
                second.close()

    def test_all_credential_fields_must_match_actual_effective_user(self):
        with connected() as (connection, _):
            before = descriptors()
            with patch.object(os, 'geteuid', return_value=os.geteuid() + 1):
                with self.assertRaises(AgentTaskError):
                    module.retain_connected_peer(connection)
            self.assertEqual(descriptors(), before)

    def test_metadata_failure_closes_only_owned_pidfd(self):
        with connected() as (connection, child):
            before = descriptors()
            with patch.object(os, 'readlink', side_effect=OSError('owned metadata probe failure')):
                with self.assertRaises(AgentTaskError):
                    module.retain_connected_peer(connection)
            self.assertEqual(descriptors(), before)
            self.assertIsNone(child.poll())

    def test_namespace_change_invalidates_retained_peer(self):
        with connected() as (connection, _):
            peer = module.retain_connected_peer(connection)
            original = os.readlink
            try:
                with patch.object(os, 'readlink', side_effect=lambda path: (
                        'user:[999999999]' if str(path).endswith('/self/ns/user') else original(path))):
                    with self.assertRaises(AgentTaskError):
                        peer.alive()
            finally:
                peer.close()

    def test_retirement_during_metadata_query_cannot_return_a_live_peer(self):
        with connected() as (connection, child):
            peer = module.retain_connected_peer(connection)
            original = os.readlink

            def retire(path):
                if not child.stdin.closed:
                    child.stdin.close()
                    self.assertEqual(child.wait(timeout=5), 0)
                return original(path)

            try:
                with patch.object(os, 'readlink', side_effect=retire):
                    with self.assertRaises(AgentTaskError):
                        peer.alive()
                self.assertFalse(peer.alive())
            finally:
                peer.close()

    def test_failed_liveness_query_is_not_a_live_identity(self):
        with connected() as (connection, _):
            peer = module.retain_connected_peer(connection)
            try:
                for mask in (select.POLLERR, select.POLLNVAL):
                    with self.subTest(mask=mask), patch.object(select, 'poll') as poll:
                        poll.return_value.poll.side_effect = lambda _timeout: [
                            (poll.return_value.register.call_args.args[0], mask)]
                        with self.assertRaises(AgentTaskError):
                            peer.alive()
            finally:
                peer.close()

    def test_missing_kernel_option_never_reopens_user_or_credential_pid(self):
        with connected() as (connection, _):
            with patch.object(module, '_peer_option', return_value=65535), patch.object(os, 'pidfd_open') as reopen:
                with self.assertRaises(AgentTaskError):
                    module.retain_connected_peer(connection)
                reopen.assert_not_called()

    def test_wrong_transport_types_are_refused_without_retained_descriptors(self):
        for family, kind in ((socket.AF_UNIX, socket.SOCK_DGRAM), (socket.AF_INET, socket.SOCK_STREAM)):
            with self.subTest(family=family, kind=kind), socket.socket(family, kind) as connection:
                before = descriptors()
                with self.assertRaises(AgentTaskError):
                    module.retain_connected_peer(connection)
                self.assertEqual(descriptors(), before)

    def test_closed_or_unconnected_stream_is_a_typed_failure(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            with self.assertRaises(AgentTaskError):
                module.retain_connected_peer(connection)
        finally:
            connection.close()
        with self.assertRaises(AgentTaskError):
            module.retain_connected_peer(connection)

    def test_unknown_numeric_abi_and_non_linux_are_refused_before_socket_access(self):
        with patch.object(module.sys, 'platform', 'win32'):
            with self.assertRaises(AgentTaskError):
                module.retain_connected_peer(None)
        with patch.object(socket, 'SO_PEERPIDFD', None, create=True), patch.object(
                module.platform, 'machine', return_value='sparc64'):
            with self.assertRaises(AgentTaskError):
                module._peer_option()



class LinuxPeerBoundaryTests(unittest.TestCase):
    def test_close_waits_for_live_identity_query_before_retiring_owned_descriptor(self):
        identity = module.LinuxPeerIdentity(1, 1, 1, 1, 'user:[1]', 'pid:[1]')
        peer = module.LinuxPeerProcess(99999, identity)
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        outcomes = []

        def snapshot(*_arguments):
            entered.set()
            if not release.wait(2):
                raise AssertionError('test identity query was not released')
            return identity

        def close_peer():
            peer.close()
            closed.set()

        with patch.object(module, '_live', return_value=True), patch.object(
                module, '_snapshot', side_effect=snapshot), patch.object(os, 'close') as close:
            query = threading.Thread(target=lambda: outcomes.append(peer.alive()))
            closer = threading.Thread(target=close_peer)
            try:
                query.start()
                self.assertTrue(entered.wait(1))
                closer.start()
                self.assertFalse(closed.wait(0.1), 'descriptor retired while its identity query was pending')
            finally:
                release.set()
                query.join(5)
                if closer.ident is not None:
                    closer.join(5)
                peer.close()
            self.assertFalse(query.is_alive() or closer.is_alive())
            self.assertEqual(outcomes, [True])
            self.assertTrue(closed.is_set())
            close.assert_called_once_with(99999)

    def test_non_linux_refuses_before_reading_or_opening_a_socket(self):
        with patch.object(module.sys, 'platform', 'win32'):
            with self.assertRaises(AgentTaskError):
                module.retain_connected_peer(None)

    def test_unknown_numeric_abi_refuses_before_socket_metadata(self):
        with patch.object(module.sys, 'platform', 'linux'), patch.object(
                socket, 'SO_PEERPIDFD', None, create=True), patch.object(
                module.platform, 'machine', return_value='sparc64'):
            with self.assertRaises(AgentTaskError):
                module.retain_connected_peer(None)

    def test_python_native_option_takes_precedence_over_numeric_abi_mapping(self):
        with patch.object(socket, 'SO_PEERPIDFD', 77, create=True), patch.object(
                module.platform, 'machine', side_effect=AssertionError('ABI fallback forbidden')):
            self.assertEqual(module._peer_option(), 77)

    def test_malformed_native_options_never_select_an_unrelated_kernel_option(self):
        for value in (True, False, 0, -1, 65536, 1.5, '77'):
            with self.subTest(value=value), patch.object(socket, 'SO_PEERPIDFD', value, create=True):
                with self.assertRaises(AgentTaskError):
                    module._peer_option()

    def test_close_failure_is_typed_and_never_retries_a_possibly_reused_descriptor(self):
        identity = module.LinuxPeerIdentity(1, 1, 1, 1, 'user:[1]', 'pid:[1]')
        peer = module.LinuxPeerProcess(99999, identity)
        with patch.object(os, 'close', side_effect=OSError('private close failure')) as close:
            with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                peer.close()
            peer.close()
            self.assertFalse(peer.alive())
            close.assert_called_once_with(99999)
