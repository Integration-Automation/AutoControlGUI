"""Socket retirement uncertainty survives every factory ownership-transfer boundary."""
from contextlib import ExitStack
from dataclasses import replace
import errno
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime import presence_channel_linux as module
from je_auto_control.utils.agent_runtime.presence_peer_linux import _RetirementUnconfirmed
from .presence_linux_test_support import native_support


def descriptors():
    return {int(name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/' + name)}


class SocketCloseFault:
    def __init__(self, target=None):
        self.target, self.attempts, self.reused = target, [], None
        self.real_close = socket.socket.close
        self.replacement = lambda connection: self.close(connection)

    def close(self, connection):
        descriptor = connection.fileno()
        self.real_close(connection)
        if self.target is not None and connection is not self.target:
            return
        self.attempts.append(descriptor)
        if self.reused is not None:
            return
        if connection.fileno() != -1 or descriptor < 0:
            raise AssertionError('socket did not release its descriptor before the injected close error')
        replacement = os.open('/dev/null', os.O_RDONLY)
        if replacement != descriptor:
            os.dup2(replacement, descriptor, inheritable=False)
            os.close(replacement)
        self.reused = descriptor
        raise OSError(errno.EIO, 'owned socket close failed after actual retirement')

    def release(self):
        if self.reused is not None:
            descriptor, self.reused = self.reused, None
            os.close(descriptor)


def refusal(operation):
    try:
        result = operation()
    except (AgentTaskError, OSError) as error:
        return error
    result.close()
    raise AssertionError('owned factory unexpectedly published a result')


@unittest.skipUnless(sys.platform == 'linux', 'native Linux socket lifetime proof required')
class SocketRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_support()

    def assert_retirement(self, failure, fault, before):
        self.assertEqual(fault.attempts, [fault.reused])
        self.assertTrue(os.fstat(fault.reused))
        self.assertEqual(descriptors(), before | {fault.reused})
        self.assertIsInstance(failure, _RetirementUnconfirmed, str(failure))

    def test_socket_configuration_rollback_preserves_retirement_uncertainty(self):
        with tempfile.TemporaryDirectory(prefix='ac-socket-config-') as runtime:
            before, fault = descriptors(), SocketCloseFault()
            try:
                with (
                    patch.object(module, '_configure', side_effect=AgentTaskError('configuration refused')),
                    patch.object(socket.socket, 'close', new=fault.replacement),
                ):
                    failure = refusal(lambda: module.LinuxListener.create(runtime))
                self.assertEqual(list(Path(runtime).iterdir()), [])
                self.assert_retirement(failure, fault, before)
            finally:
                fault.release()

    def test_capture_rollback_before_and_after_peer_retention_is_unconfirmed(self):
        for boundary in ('configuration', 'owner'):
            with self.subTest(boundary=boundary), ExitStack() as stack:
                left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                stack.callback(right.close)
                module._configure(left)
                before = descriptors() - {left.fileno()}
                fault = SocketCloseFault(left)
                stack.callback(fault.release)
                name = '_configure' if boundary == 'configuration' else '_Owner'
                stack.enter_context(patch.object(module, name, side_effect=AgentTaskError('capture refused')))
                stack.enter_context(patch.object(socket.socket, 'close', new=fault.replacement))
                failure = refusal(lambda: module._capture(left))
                self.assert_retirement(failure, fault, before)

    def test_public_listener_creation_rollback_preserves_socket_close_failure(self):
        with tempfile.TemporaryDirectory(prefix='ac-socket-create-') as runtime:
            before, fault = descriptors(), SocketCloseFault()
            try:
                with (
                    patch.object(socket.socket, 'listen', side_effect=OSError(errno.EIO, 'listen refused')),
                    patch.object(socket.socket, 'close', new=fault.replacement),
                ):
                    failure = refusal(lambda: module.LinuxListener.create(runtime))
                self.assertEqual(list(Path(runtime).iterdir()), [])
                self.assert_retirement(failure, fault, before)
            finally:
                fault.release()

    def test_connect_rollback_before_and_after_capture_keeps_uncertainty(self):
        for boundary in ('endpoint', 'identity'):
            with (
                self.subTest(boundary=boundary),
                tempfile.TemporaryDirectory(prefix='ac-socket-connect-') as runtime,
                module.LinuxListener.create(runtime) as listener,
                ExitStack() as stack,
            ):
                endpoint = listener.endpoint
                if boundary == 'endpoint':
                    stack.enter_context(patch.object(module, '_EndpointCheck', side_effect=AgentTaskError('refused')))
                else:
                    endpoint = replace(endpoint, listener_process=replace(endpoint.listener_process, birth=1))
                before, fault = descriptors(), SocketCloseFault()
                stack.callback(fault.release)
                stack.enter_context(patch.object(socket.socket, 'close', new=fault.replacement))
                failure = refusal(lambda: module.LinuxChannel.connect(endpoint, timeout=1))
                self.assert_retirement(failure, fault, before)

    def test_accept_capture_failure_remains_unconfirmed_after_listener_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='ac-socket-accept-') as runtime, ExitStack() as stack:
            before = descriptors()
            listener = module.LinuxListener.create(runtime)
            client = module.LinuxChannel.connect(listener.endpoint, timeout=1)
            client_descriptors = descriptors() - before
            listener_resources = listener._owner._state.resources
            listener_descriptors = {listener_resources.connection.fileno(), listener_resources.files.parent_fd,
                                    listener_resources.files.directory_fd}
            client_descriptors -= listener_descriptors
            stack.callback(client.close)
            fault = SocketCloseFault()
            stack.callback(fault.release)
            stack.enter_context(patch.object(module, 'retain_connected_peer', side_effect=AgentTaskError('refused')))
            stack.enter_context(patch.object(socket.socket, 'close', new=fault.replacement))
            failure = refusal(lambda: listener.accept(timeout=1))
            self.assertEqual(descriptors(), before | client_descriptors | {fault.reused})
            self.assertEqual(fault.attempts.count(fault.reused), 1)
            self.assertTrue(os.fstat(fault.reused))
            self.assertIsInstance(failure, _RetirementUnconfirmed, str(failure))
            self.assertTrue(listener._owner._state.unconfirmed)
            with self.assertRaises(_RetirementUnconfirmed):
                listener.close()

    def test_plain_configuration_failure_does_not_claim_retirement_uncertainty(self):
        with tempfile.TemporaryDirectory(prefix='ac-socket-plain-') as runtime:
            for original in (AgentTaskError('configuration refused'), TypeError('owned programming error')):
                before = descriptors()
                with (
                    patch.object(module, '_configure', side_effect=original),
                    self.assertRaises(type(original)) as caught,
                ):
                    module.LinuxListener.create(runtime)
                self.assertIs(caught.exception, original)
                self.assertNotIsInstance(caught.exception, _RetirementUnconfirmed)
                self.assertEqual(descriptors(), before)
