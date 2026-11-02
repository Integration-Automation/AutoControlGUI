"""Deliver clipboard data under its captured local authority and concrete connection owner."""
from dataclasses import dataclass, field
from typing import Any, Callable
import weakref

from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardSyncError


def apply_clipboard(kind: str, data: Any) -> None:
    """Apply one decoded text/image payload using lazily loaded native helpers, without sending it onward."""
    # pylint: disable-next=import-outside-toplevel  # reason: native providers load only for an authorised delivery
    from je_auto_control.utils.clipboard.clipboard import set_clipboard, set_clipboard_image
    if kind == 'text':
        set_clipboard(data)
    elif kind == 'image':
        set_clipboard_image(data)
    else:
        raise ClipboardSyncError(f'unsupported clipboard kind: {kind!r}')


@dataclass(frozen=True)
class ClipboardDelivery:
    """One queued local delivery; authority is captured at registration, never inferred from a callback thread."""
    peer: object
    kind: str
    data: Any
    authority: DeferredAuthorization

    def dispatch(self, active: Callable[[object], bool], apply: Callable[[str, Any], None]) -> bool:
        """Refresh the original user's permission and recheck ownership before any native clipboard write."""
        if not active(self.peer):
            return False
        with self.authority.scope():
            if not active(self.peer):
                return False
            apply(self.kind, self.data)
        return True


@dataclass(frozen=True, eq=False)
class ClipboardReceiver:
    """Bind once before starting a peer; callbacks must not make that peer own itself or its Qt panel."""
    authority: DeferredAuthorization
    deliver: Callable[[ClipboardDelivery], object]
    _peer_ref: weakref.ReferenceType[object] | None = field(default=None, init=False, repr=False)

    def bind(self, peer: object) -> None:
        """Pin the original identity weakly, refusing any later retargeting even after that peer is gone."""
        if self._peer_ref is not None:
            raise ClipboardSyncError('the clipboard receiver is already bound to its original peer')
        try:
            reference = weakref.ref(peer)
        except TypeError as error:
            raise ClipboardSyncError('the clipboard peer must support weak references') from error
        object.__setattr__(self, '_peer_ref', reference)

    def __call__(self, kind: str, data: Any) -> None:
        """Keep the concrete origin alive only in an actual queued delivery; retain its original authority."""
        peer = self._peer_ref() if self._peer_ref is not None else None
        if peer is not None:
            self.deliver(ClipboardDelivery(peer, kind, data, self.authority))
