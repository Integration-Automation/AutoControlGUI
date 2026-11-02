"""Native capability skips shared by Linux channel and endpoint component tests."""
import errno
import os
import socket
import unittest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_peer_linux import _socket_constant


def native_support():
    """Require actual kernel socket options; never substitute a fake native success."""
    try:
        if not getattr(socket, 'MSG_CMSG_CLOEXEC', 0) or not hasattr(socket.socket, 'recvmsg'):
            raise unittest.SkipTest('native Python lacks atomic ancillary descriptor receipt')
        for name in ('SCM_PIDFD', 'SCM_RIGHTS', 'SCM_CREDENTIALS'):
            _socket_constant(name)
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        with left, right:
            left.setsockopt(socket.SOL_SOCKET, _socket_constant('SO_PASSPIDFD'), 1)
            descriptor = left.getsockopt(socket.SOL_SOCKET, _socket_constant('SO_PEERPIDFD'))
            os.close(descriptor)
    except (AttributeError, AgentTaskError) as error:
        raise unittest.SkipTest('native Linux socket credential ABI is unavailable') from error
    except OSError as error:
        if error.errno in {errno.ENOPROTOOPT, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL}:
            raise unittest.SkipTest('native kernel lacks sequenced-packet pidfd credential support') from error
        raise
