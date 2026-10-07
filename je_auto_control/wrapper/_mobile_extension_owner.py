"""Lazy owner-bound extension dispatch and native file/argument validation."""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional, TYPE_CHECKING

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.wrapper._mobile_client_owner import LazyMobileHandle
from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError, bounded_timeout
from je_auto_control.wrapper._mobile_extension_models import MobileExtension, MobileExtensionSpec

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


class ExtensionOwner:
    """Guard calls, late factories and cleanup without executing factories in probes."""

    def __init__(self, session: DeviceSession, spec: Optional[MobileExtensionSpec]) -> None:
        self.session, self.spec = session, spec
        self._owner = LazyMobileHandle(None, session.ensure_open, lambda adapter: adapter.close())

    def _create(self) -> MobileExtension:
        if self.spec is not None:
            adapter = self.spec.factory(self.session.context, self.session.ensure_open)
        else:
            # pylint: disable-next=import-outside-toplevel  # reason: native default is lazy and Android-only
            from je_auto_control.android.extensions import AndroidExtension
            adapter = AndroidExtension(self.session)
        if adapter.context != self.session.context:
            raise DeviceSessionError('extension factory returned a different device owner')
        return adapter

    def execute(self, operation: str, params: Mapping[str, Any]) -> Any:
        """Never dispatch or return a successful result after owner revocation."""
        self.session.ensure_open()
        try:
            result = getattr(self._owner.get(self._create), operation)(**params)
        except AutoControlException:
            raise
        except Exception as failure:  # reason: optional adapter exceptions stay within the framework error family
            raise DeviceSessionError('mobile extension failed; native state may be unknown') from failure
        self.session.ensure_open()
        return result

    def close(self) -> None:
        """Reclaim only the adapter created by this owner; retry failed cleanup."""
        self._owner.close()


def _local_path(value: Any, operation: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeviceSessionError('extension requires a nonempty local file path')
    path = scoped_path(value, operation=operation)
    if operation == 'read' and not path.is_file():
        raise DeviceSessionError('extension input file does not exist')
    return str(path)


def validated_options(operation: str, options: Mapping[str, Any], context: DeviceContext) -> dict[str, Any]:
    """Reject malformed requests before creating or connecting any native adapter."""
    fields = {'install': {'file_path'}, 'files': {'action', 'local_path', 'remote_path'},
              'clipboard': {'text'}, 'recording': {'file_path', 'duration_s'}}
    if set(options) - fields[operation]:
        raise DeviceSessionError('unknown mobile extension options')
    params = dict(options)
    if operation == 'clipboard':
        text = params.get('text')
        if text is not None and (not isinstance(text, str) or '\x00' in text):
            raise DeviceSessionError('clipboard text must be Unicode without NUL')
        return params
    if operation == 'files':
        return _file_options(params)
    params['file_path'] = _local_path(params.get('file_path'), 'read' if operation == 'install' else 'write')
    if operation == 'recording':
        params['duration_s'] = bounded_timeout(context.timeout_s, params.get('duration_s'))
    return params


def _file_options(params: dict[str, Any]) -> dict[str, Any]:
    action, remote = params.get('action'), params.get('remote_path')
    if action not in ('push', 'pull'):
        raise DeviceSessionError('file action must be push or pull')
    # Conservative native path syntax: ADB may interpret a remote path through its shell.
    if not isinstance(remote, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', remote, re.ASCII):
        raise DeviceSessionError('remote path must be an absolute native path without shell metacharacters')
    if '..' in remote.split('/'):
        raise DeviceSessionError('remote file path cannot traverse parent directories')
    params['local_path'] = _local_path(params.get('local_path'), 'read' if action == 'push' else 'write')
    return params
