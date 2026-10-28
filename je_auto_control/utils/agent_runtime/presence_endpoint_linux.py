"""Own protected Linux socket paths without stale-path reuse or recursive cleanup."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import socket
import stat

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_peer_linux import (
    LinuxPeerIdentity, _RetirementUnconfirmed, _account, _birth, _namespaces,
)


@dataclass(frozen=True)
class FileIdentity:
    """The observed filesystem object, including its required protection mode."""

    device: int
    inode: int
    owner: int
    mode: int


@dataclass(frozen=True)
class _UnverifiedPath:
    """Creation succeeded, but no identity authorizes pathname cleanup yet."""


@dataclass(frozen=True)
class LinuxEndpoint:
    """Immutable launch metadata, useful only when received through a trusted launch path.

    Permissions do not isolate hostile same-UID or root processes. Path checks followed
    by unlink are not atomic compare-inode-and-unlink. Same-account pathname mutation
    must be trusted. A pathname socket inode is unrelated to a connected socket fd inode.
    """

    directory: str
    directory_identity: FileIdentity
    socket_name: str
    socket_identity: FileIdentity
    listener_process: LinuxPeerIdentity


def _identity(value: os.stat_result) -> FileIdentity:
    return FileIdentity(value.st_dev, value.st_ino, value.st_uid, value.st_mode)


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, 'O_DIRECTORY') | getattr(os, 'O_NOFOLLOW') | getattr(os, 'O_CLOEXEC')


def _close_directory(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        raise _RetirementUnconfirmed('Linux endpoint descriptor retirement is unconfirmed') from None


def _check_directory(descriptor: int, *, private: bool) -> FileIdentity:
    value = os.fstat(descriptor)
    if not stat.S_ISDIR(value.st_mode) or os.get_inheritable(descriptor):
        raise AgentTaskError('Linux runtime directory type or inheritance is invalid')
    if private:
        valid = value.st_uid == getattr(os, 'geteuid')() and stat.S_IMODE(value.st_mode) & 0o7077 == 0
    else:
        sticky = bool(value.st_mode & stat.S_ISVTX)
        valid = value.st_uid in {0, getattr(os, 'geteuid')()} and (not value.st_mode & 0o022 or sticky)
    if not valid:
        raise AgentTaskError('Linux runtime directory owner or permissions are unsafe')
    return _identity(value)


def _open_directory(path: str | Path) -> int:
    if not isinstance(path, (str, Path)):
        raise AgentTaskError('Linux runtime directory path is invalid')
    value = os.fspath(path)
    if not isinstance(value, str) or not value.startswith('/') or '\0' in value:
        raise AgentTaskError('Linux runtime directory must be an absolute path')
    parts = value.split('/')[1:]
    if not parts or any(part in {'', '.', '..'} for part in parts):
        raise AgentTaskError('Linux runtime directory path must have canonical components')
    descriptor = os.open('/', _directory_flags())
    try:
        _check_directory(descriptor, private=False)
        for index, part in enumerate(parts):
            next_descriptor = os.open(part, _directory_flags(), dir_fd=descriptor)
            old, descriptor = descriptor, next_descriptor
            _close_directory(old)
            _check_directory(descriptor, private=index == len(parts) - 1)
        result, descriptor = descriptor, -1
        return result
    finally:
        if descriptor >= 0:
            owned, descriptor = descriptor, -1
            _close_directory(owned)


def _self_identity() -> LinuxPeerIdentity:
    pid, uid, gid = os.getpid(), getattr(os, 'geteuid')(), getattr(os, 'getegid')()
    _account('self', uid, gid)
    return LinuxPeerIdentity(pid, uid, gid, _birth(pid), *_namespaces('self'))


def _check_socket(directory_fd: int, name: str, expected: FileIdentity | None = None) -> FileIdentity:
    value = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    result = _identity(value)
    protected = value.st_uid == getattr(os, 'geteuid')() and stat.S_IMODE(value.st_mode) == 0o600
    if not stat.S_ISSOCK(value.st_mode) or not protected:
        raise AgentTaskError('Linux endpoint socket owner or permissions are unsafe')
    if expected is not None and result != expected:
        raise AgentTaskError('Linux endpoint socket identity changed')
    return result


class _EndpointFiles:
    def __init__(self, runtime: str | Path) -> None:
        if not isinstance(runtime, (str, Path)):
            raise AgentTaskError('Linux runtime directory path is invalid')
        self.parent_fd: int | None = None
        self.directory_fd: int | None = None
        self.name = 'presence-' + secrets.token_hex(12)
        self.directory = str(Path(runtime) / self.name)
        self.directory_identity: FileIdentity | _UnverifiedPath | None = None
        self.socket_identity: FileIdentity | _UnverifiedPath | None = None
        self.socket_name = 'channel.sock'
        self.parent_fd = _open_directory(runtime)

    def bind(self, connection: socket.socket) -> LinuxEndpoint:
        """Record each created object before advancing to the next creation step."""
        os.mkdir(self.name, 0o700, dir_fd=self.parent_fd)
        self.directory_identity = _UnverifiedPath()
        self.directory_identity = _identity(os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False))
        self.directory_fd = os.open(self.name, _directory_flags(), dir_fd=self.parent_fd)
        if _check_directory(self.directory_fd, private=True) != self.directory_identity:
            raise AgentTaskError('Linux newly created directory identity changed')
        getattr(os, 'fchmod')(self.directory_fd, 0o700)
        self.directory_identity = _check_directory(self.directory_fd, private=True)
        connection.bind(self.address)
        self.socket_identity = _UnverifiedPath()
        self.socket_identity = _identity(os.stat(self.socket_name, dir_fd=self.directory_fd, follow_symlinks=False))
        os.chmod(self.socket_name, 0o600, dir_fd=self.directory_fd, follow_symlinks=False)
        self.socket_identity = _check_socket(self.directory_fd, self.socket_name)
        return LinuxEndpoint(self.directory, self.directory_identity, self.socket_name,
                             self.socket_identity, _self_identity())

    @property
    def address(self) -> str:
        """Bind through the retained directory handle without resolving ancestor paths again."""
        return f'/proc/self/fd/{self.directory_fd}/{self.socket_name}'

    def _remove_paths(self) -> None:
        if isinstance(self.directory_identity, _UnverifiedPath) or isinstance(self.socket_identity, _UnverifiedPath):
            raise _RetirementUnconfirmed('Linux created endpoint identity is unverified; retirement is unconfirmed')
        if self.socket_identity is not None:
            actual = _identity(os.stat(self.socket_name, dir_fd=self.directory_fd, follow_symlinks=False))
            if actual != self.socket_identity:
                raise AgentTaskError('Linux endpoint replacement preserved; retirement is unconfirmed')
            os.unlink(self.socket_name, dir_fd=self.directory_fd)
            self.socket_identity = None
        if self.directory_identity is not None:
            actual = _identity(os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False))
            if actual != self.directory_identity:
                raise AgentTaskError('Linux endpoint directory replacement preserved; retirement is unconfirmed')
            os.rmdir(self.name, dir_fd=self.parent_fd)
            self.directory_identity = None

    def close(self) -> None:
        """Preserve replacements and unknown contents while retiring all owned directory handles."""
        failure = False
        try:
            self._remove_paths()
        except (OSError, NotImplementedError, AgentTaskError):
            failure = True
        self.socket_identity = None
        self.directory_identity = None
        for field in ('directory_fd', 'parent_fd'):
            descriptor = getattr(self, field)
            setattr(self, field, None)
            if descriptor is not None:
                try:
                    _close_directory(descriptor)
                except _RetirementUnconfirmed:
                    failure = True
        if failure:
            raise _RetirementUnconfirmed('Linux endpoint retirement is unconfirmed')


class _EndpointCheck:
    def __init__(self, endpoint: LinuxEndpoint) -> None:
        if not isinstance(endpoint, LinuxEndpoint) or endpoint.socket_name != 'channel.sock':
            raise AgentTaskError('Linux endpoint description is invalid')
        self.endpoint = endpoint
        self.descriptor = _open_directory(endpoint.directory)
        try:
            self.verify()
        except BaseException:
            self.close()
            raise

    @property
    def address(self) -> str:
        """Connect through the checked directory handle."""
        return f'/proc/self/fd/{self.descriptor}/{self.endpoint.socket_name}'

    def verify(self) -> None:
        """Check opened directory and current path against the trusted immutable endpoint."""
        if _check_directory(self.descriptor, private=True) != self.endpoint.directory_identity:
            raise AgentTaskError('Linux endpoint directory identity changed')
        _check_socket(self.descriptor, self.endpoint.socket_name, self.endpoint.socket_identity)
        path_descriptor = _open_directory(self.endpoint.directory)
        try:
            if _identity(os.fstat(path_descriptor)) != self.endpoint.directory_identity:
                raise AgentTaskError('Linux endpoint path was replaced')
        finally:
            owned, path_descriptor = path_descriptor, -1
            _close_directory(owned)

    def close(self) -> None:
        """Retire the checked directory handle once, including after a close error."""
        descriptor, self.descriptor = self.descriptor, -1
        if descriptor >= 0:
            _close_directory(descriptor)
