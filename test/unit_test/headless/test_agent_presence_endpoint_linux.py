"""Owned Linux endpoint permissions, component traversal and replacement preservation."""
from dataclasses import replace
import errno
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime import presence_channel_linux as module
from je_auto_control.utils.agent_runtime import presence_endpoint_linux as endpoint_module
from je_auto_control.utils.agent_runtime.presence_peer_linux import _RetirementUnconfirmed
from .presence_linux_test_support import native_support


def descriptors():
    return {int(name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/' + name)}


class DirectoryCloseFault:
    def __init__(self, mode):
        self.mode, self.opened, self.injected, self.reused = mode, [], False, None
        self.real_close = os.close
        self.real_open = endpoint_module._open_directory
        self.real_check = endpoint_module._check_socket

    def open_directory(self, path):
        descriptor = self.real_open(path)
        self.opened.append(descriptor)
        return descriptor

    def check_socket(self, *args):
        if self.mode == 'constructor':
            raise AgentTaskError('owned constructor metadata failure')
        return self.real_check(*args)

    def matches(self, descriptor):
        if self.mode == 'traversal':
            return stat.S_ISDIR(os.fstat(descriptor).st_mode)
        minimum = {'constructor': 1, 'verification': 2, 'final': 3}[self.mode]
        if len(self.opened) < minimum:
            return False
        target = self.opened[1] if self.mode == 'verification' else self.opened[0]
        return descriptor == target

    def close(self, descriptor):
        if not self.injected and self.matches(descriptor):
            self.injected = True
            self.real_close(descriptor)
            replacement = os.open('/dev/null', os.O_RDONLY)
            if replacement != descriptor:
                os.dup2(replacement, descriptor, inheritable=False)
                self.real_close(replacement)
            self.reused = descriptor
            raise OSError(errno.EIO, 'injected directory close failure after retirement')
        self.real_close(descriptor)

    def release(self):
        if self.reused is not None:
            descriptor, self.reused = self.reused, None
            self.real_close(descriptor)


def refused_listener(runtime):
    try:
        listener = module.LinuxListener.create(runtime)
    except (AgentTaskError, NotImplementedError) as error:
        return error
    listener.close()
    raise AssertionError('owned listener creation unexpectedly succeeded')


def refused_connection(endpoint):
    try:
        channel = module.LinuxChannel.connect(endpoint, timeout=1)
    except (AgentTaskError, NotImplementedError) as error:
        return error
    channel.close()
    raise AssertionError('owned endpoint connection unexpectedly succeeded')


@unittest.skipUnless(sys.platform == 'linux', 'native Linux filesystem endpoint ownership required')
class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_support()

    def test_creation_without_identity_preserves_paths_and_reports_retirement_unconfirmed(self):
        for kind in ('directory', 'socket'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix='ac-create-fault-') as runtime:
                before = descriptors()
                original = os.stat
                injected = []

                def fail_stat(path, *args, **kwargs):
                    match = str(path).startswith('presence-') if kind == 'directory' else path == 'channel.sock'
                    if match and kwargs.get('dir_fd') is not None and not injected:
                        injected.append(str(path))
                        raise OSError(errno.EIO, 'owned post-creation identity failure')
                    return original(path, *args, **kwargs)

                with patch.object(endpoint_module.os, 'stat', side_effect=fail_stat):
                    failure = refused_listener(runtime)
                remaining = list(Path(runtime).rglob('*'))
                self.assertTrue(injected)
                self.assertEqual(len(remaining), 1 if kind == 'directory' else 2)
                self.assertTrue(any(path.is_dir() for path in remaining))
                self.assertEqual(descriptors(), before)
                self.assertIsInstance(failure, _RetirementUnconfirmed, str(failure))

    def test_unavailable_chmod_refuses_and_cleanup_uncertainty_takes_precedence(self):
        for cleanup_error in (None, OSError, NotImplementedError):
            with (
                self.subTest(cleanup_error=cleanup_error),
                tempfile.TemporaryDirectory(prefix='ac-no-chmod-') as runtime,
            ):
                before = descriptors()
                unlink = os.unlink if cleanup_error is None else cleanup_error('owned cleanup failure')
                with (
                    patch.object(endpoint_module.os, 'chmod', side_effect=NotImplementedError('chmod unavailable')),
                    patch.object(endpoint_module.os, 'unlink', side_effect=unlink),
                ):
                    failure = refused_listener(runtime)
                after = descriptors()
                for descriptor in after - before:
                    os.close(descriptor)
                self.assertEqual(after, before, 'failed construction leaked owned directory handles')
                remaining = list(Path(runtime).rglob('*'))
                self.assertEqual(len(remaining), 0 if cleanup_error is None else 2)
                expected = AgentTaskError if cleanup_error is None else _RetirementUnconfirmed
                self.assertIsInstance(failure, expected, str(failure))

    def test_unavailable_directory_open_refuses_connection_without_publishing_or_leaking(self):
        with (
            tempfile.TemporaryDirectory(prefix='ac-no-directory-open-') as runtime,
            module.LinuxListener.create(runtime) as listener,
        ):
            before = descriptors()
            with patch.object(endpoint_module, '_open_directory',
                              side_effect=NotImplementedError('dir_fd unavailable')):
                failure = refused_connection(listener.endpoint)
            self.assertEqual(descriptors(), before)
            self.assertTrue((Path(listener.endpoint.directory) / 'channel.sock').is_socket())
            self.assertIsInstance(failure, AgentTaskError, str(failure))

    def test_traversal_close_failure_is_unconfirmed_and_never_retries_reused_number(self):
        with tempfile.TemporaryDirectory(prefix='ac-traversal-close-') as runtime:
            before = descriptors()
            fault = DirectoryCloseFault('traversal')
            try:
                with patch.object(endpoint_module.os, 'close', side_effect=fault.close):
                    failure = refused_listener(runtime)
                self.assertTrue(fault.injected)
                self.assertEqual(descriptors(), before | {fault.reused})
                self.assertTrue(os.fstat(fault.reused))
                self.assertEqual(list(Path(runtime).iterdir()), [])
                self.assertIsInstance(failure, _RetirementUnconfirmed, str(failure))
            finally:
                fault.release()
            self.assertEqual(descriptors(), before)

    def test_checked_directory_close_failures_remain_unconfirmed_at_every_retirement_boundary(self):
        for mode in ('constructor', 'verification', 'final'):
            with (
                self.subTest(mode=mode),
                tempfile.TemporaryDirectory(prefix='ac-check-close-') as runtime,
                module.LinuxListener.create(runtime) as listener,
            ):
                before = descriptors()
                fault = DirectoryCloseFault(mode)
                try:
                    with (
                        patch.object(endpoint_module, '_open_directory', side_effect=fault.open_directory),
                        patch.object(endpoint_module, '_check_socket', side_effect=fault.check_socket),
                        patch.object(endpoint_module.os, 'close', side_effect=fault.close),
                    ):
                        failure = refused_connection(listener.endpoint)
                    self.assertTrue(fault.injected)
                    self.assertEqual(descriptors(), before | {fault.reused})
                    self.assertTrue(os.fstat(fault.reused))
                    self.assertIsInstance(failure, _RetirementUnconfirmed, str(failure))
                finally:
                    fault.release()
                self.assertEqual(descriptors(), before)

    def test_owned_temporary_runtime_beneath_sticky_tmp_is_supported(self):
        before = descriptors()
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            with module.LinuxListener.create(runtime) as listener:
                self.assertEqual(Path(listener.endpoint.directory).stat().st_mode & 0o7777, 0o700)
            self.assertEqual(list(Path(runtime).iterdir()), [])
        self.assertEqual(descriptors(), before)

    def test_runtime_must_be_real_owned_private_directory(self):
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            directory = Path(runtime) / 'runtime'
            directory.mkdir(mode=0o700)
            link = Path(runtime) / 'link'
            link.symlink_to(directory, target_is_directory=True)
            nested = directory / 'nested'
            nested.mkdir(mode=0o700)
            for invalid in (str(link), str(link / 'nested'), str(directory / '..' / 'runtime'), 'relative', '\0'):
                before = descriptors()
                with self.subTest(path=invalid), self.assertRaises(AgentTaskError):
                    module.LinuxListener.create(invalid)
                self.assertEqual(descriptors(), before)
            for mode in (0o755, 0o770, 0o777, 0o1700):
                directory.chmod(mode)
                with self.subTest(mode=mode), self.assertRaises(AgentTaskError):
                    module.LinuxListener.create(directory)
            directory.chmod(0o700)
            with patch.object(endpoint_module.os, 'geteuid', return_value=os.geteuid() + 1):
                with self.assertRaises(AgentTaskError):
                    module.LinuxListener.create(directory)

    def test_no_umask_change_and_no_stale_endpoint_reuse(self):
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            with patch.object(endpoint_module.secrets, 'token_hex', return_value='a' * 24), patch.object(
                    os, 'umask', side_effect=AssertionError('process-wide umask mutation forbidden')):
                with module.LinuxListener.create(runtime) as first:
                    before = descriptors()
                    with self.assertRaises(AgentTaskError):
                        module.LinuxListener.create(runtime)
                    self.assertEqual(descriptors(), before)
                    self.assertTrue((Path(first.endpoint.directory) / 'channel.sock').is_socket())

    def test_unknown_contents_survive_failed_directory_cleanup(self):
        before = descriptors()
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            listener = module.LinuxListener.create(runtime)
            directory = Path(listener.endpoint.directory)
            marker = directory / 'unknown'
            marker.write_bytes(b'owned test marker')
            with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                listener.close()
            self.assertEqual(marker.read_bytes(), b'owned test marker')
            self.assertFalse((directory / 'channel.sock').exists())
            with self.assertRaises(AgentTaskError):
                listener.close()
        self.assertEqual(descriptors(), before)

    def test_replacement_socket_is_preserved_and_handles_retire(self):
        before = descriptors()
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            listener = module.LinuxListener.create(runtime)
            directory = Path(listener.endpoint.directory)
            path = directory / 'channel.sock'
            path.rename(directory / 'original.sock')
            with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as replacement:
                replacement.bind(str(path))
                identity = path.stat()
                with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                    listener.close()
                self.assertEqual(path.stat().st_ino, identity.st_ino)
                self.assertTrue((directory / 'original.sock').exists())
        self.assertEqual(descriptors(), before)

    def test_replacement_directory_is_preserved_by_handle_relative_cleanup(self):
        before = descriptors()
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            listener = module.LinuxListener.create(runtime)
            directory = Path(listener.endpoint.directory)
            moved = Path(runtime) / 'moved'
            directory.rename(moved)
            directory.mkdir(mode=0o700)
            marker = directory / 'untouched'
            marker.write_bytes(b'test')
            with self.assertRaisesRegex(AgentTaskError, 'retirement is unconfirmed'):
                listener.close()
            self.assertEqual(marker.read_bytes(), b'test')
            self.assertEqual(list(moved.iterdir()), [])
        self.assertEqual(descriptors(), before)

    def test_failed_connects_do_not_remove_listener_or_leak(self):
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            with module.LinuxListener.create(runtime) as listener:
                endpoint = listener.endpoint
                before = descriptors()
                invalid = [replace(endpoint, socket_name='../channel.sock'),
                           replace(endpoint, directory_identity=replace(endpoint.directory_identity, inode=1)),
                           replace(endpoint, socket_identity=replace(endpoint.socket_identity, inode=1))]
                for value in invalid:
                    with self.subTest(endpoint=value), self.assertRaises(AgentTaskError):
                        module.LinuxChannel.connect(value, timeout=1)
                    self.assertEqual(descriptors(), before)
                self.assertTrue((Path(endpoint.directory) / 'channel.sock').is_socket())

    def test_symlink_socket_and_changed_permissions_refuse_connect(self):
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            listener = module.LinuxListener.create(runtime)
            path = Path(listener.endpoint.directory) / 'channel.sock'
            path.chmod(0o666)
            with self.assertRaises(AgentTaskError):
                module.LinuxChannel.connect(listener.endpoint, timeout=1)
            path.chmod(0o600)
            path.rename(path.with_name('old.sock'))
            path.symlink_to(path.with_name('old.sock'))
            with self.assertRaises(AgentTaskError):
                module.LinuxChannel.connect(listener.endpoint, timeout=1)
            with self.assertRaises(AgentTaskError):
                listener.close()

    def test_listen_failure_rolls_back_only_created_paths(self):
        with tempfile.TemporaryDirectory(prefix='ac-endpoint-') as runtime:
            before = descriptors()
            with patch.object(module.socket.socket, 'listen', side_effect=OSError('owned fault')):
                with self.assertRaises(AgentTaskError):
                    module.LinuxListener.create(runtime)
            self.assertEqual(descriptors(), before)
            self.assertEqual(list(Path(runtime).iterdir()), [])
