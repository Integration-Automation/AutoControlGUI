"""Ancillary refusal closes all actual owned descriptors once, including failed retirement."""
import os
import socket
import struct
import sys
import unittest
from unittest.mock import Mock, patch

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime import presence_messages_linux as module
from je_auto_control.utils.agent_runtime.presence_peer_linux import _socket_constant
from .presence_linux_test_support import native_support


@unittest.skipUnless(sys.platform == 'linux', 'Linux ancillary descriptor ABI required')
class MessageOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_support()

    def test_all_complete_pidfd_and_rights_entries_are_owned_even_with_malformed_lengths(self):
        pidfd_kind = _socket_constant('SCM_PIDFD')
        ancillary = [(socket.SOL_SOCKET, pidfd_kind, struct.pack('iii', 42, -24, 43) + b'x'),
                     (socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack('ii', 43, 44)),
                     (socket.SOL_SOCKET, 65535, struct.pack('i', 99)),
                     (65535, pidfd_kind, struct.pack('i', 98))]
        self.assertEqual(module._owned_descriptors(ancillary, module._ancillary_abi()), {42, 43, 44})

    def test_close_failure_attempts_remaining_owned_fds_without_reclosing_reused_number(self):
        owned = {os.open('/dev/null', os.O_RDONLY) for _ in range(3)}
        original = owned.copy()
        closed = []
        reused = []
        real_close = os.close

        def close(descriptor):
            closed.append(descriptor)
            real_close(descriptor)
            if not reused:
                reused.append(os.open('/dev/null', os.O_RDONLY))
                self.assertEqual(reused[0], descriptor)
                raise OSError('close reported failure after retiring the descriptor')

        try:
            with patch.object(module.os, 'close', side_effect=close):
                with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                    module._release(owned)
                module._release(owned)
            self.assertEqual(set(closed), original)
            self.assertEqual(len(closed), len(original))
            self.assertEqual(owned, set())
            self.assertTrue(os.fstat(reused[0]))
        finally:
            for descriptor in reused:
                real_close(descriptor)

    def test_missing_extra_duplicate_and_unknown_controls_never_reach_identity_queries(self):
        credential_kind, pidfd_kind = _socket_constant('SCM_CREDENTIALS'), _socket_constant('SCM_PIDFD')
        for shape in ('missing_pidfd', 'missing_cred', 'duplicate', 'rights', 'unknown', 'malformed_pidfd'):
            descriptors = [os.open('/dev/null', os.O_RDONLY) for _ in range(2)]
            credentials = (socket.SOL_SOCKET, credential_kind,
                           struct.pack('iII', os.getpid(), os.getuid(), os.getgid()))
            pidfd = (socket.SOL_SOCKET, pidfd_kind, struct.pack('i', descriptors[0]))
            rights = (socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack('i', descriptors[1]))
            malformed = (socket.SOL_SOCKET, pidfd_kind, struct.pack('ii', *descriptors) + b'x')
            controls = {
                'missing_pidfd': [credentials],
                'missing_cred': [pidfd],
                'duplicate': [credentials, pidfd, pidfd],
                'rights': [credentials, pidfd, rights],
                'unknown': [credentials, pidfd, (socket.SOL_SOCKET, 65535, b'unknown')],
                'malformed_pidfd': [credentials, malformed],
            }[shape]
            received = module._owned_descriptors(controls, module._ancillary_abi())
            connection = Mock()
            connection.recvmsg.return_value = (b'{}', controls, 0, None)
            try:
                with self.subTest(shape=shape), patch.object(module, '_snapshot') as snapshot:
                    with self.assertRaises(AgentTaskError):
                        module._receive(connection, Mock())
                    snapshot.assert_not_called()
                for descriptor in received:
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
            finally:
                for descriptor in set(descriptors) - received:
                    os.close(descriptor)

    def test_negative_pidfd_never_enters_owned_set_or_queries_original_peer(self):
        pidfd_kind = _socket_constant('SCM_PIDFD')
        controls = [(socket.SOL_SOCKET, _socket_constant('SCM_CREDENTIALS'),
                     struct.pack('iII', os.getpid(), os.getuid(), os.getgid())),
                    (socket.SOL_SOCKET, pidfd_kind, struct.pack('i', -24))]
        connection, peer = Mock(), Mock()
        connection.recvmsg.return_value = (b'{}', controls, 0, None)
        with patch.object(os, 'close') as close, patch.object(module, '_snapshot') as snapshot:
            with self.assertRaises(AgentTaskError):
                module._receive(connection, peer)
            close.assert_not_called()
            snapshot.assert_not_called()
            peer.alive.assert_not_called()

    def test_unknown_abi_and_missing_cmsg_cloexec_refuse_before_consumption(self):
        connection = Mock(spec=socket.socket)
        with patch.object(socket, 'MSG_CMSG_CLOEXEC', 0):
            with self.assertRaises(AgentTaskError):
                module._configure(connection)
        with patch.object(socket, 'SCM_PIDFD', None, create=True), patch(
                'je_auto_control.utils.agent_runtime.presence_peer_linux.platform.machine', return_value='sparc64'):
            with self.assertRaises(AgentTaskError):
                module._receive(connection, Mock())
        connection.recvmsg.assert_not_called()

    def test_missing_descriptor_control_abi_refuses_before_receiving_owned_fds(self):
        connection = Mock(spec=socket.socket)
        for name in ('SCM_CREDENTIALS', 'SCM_RIGHTS'):
            with self.subTest(name=name), patch.object(socket, name, None):
                with self.assertRaises(AgentTaskError):
                    module._receive(connection, Mock())
        connection.recvmsg.assert_not_called()
