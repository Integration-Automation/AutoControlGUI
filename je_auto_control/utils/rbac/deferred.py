"""Bind delayed work to its registrant and revalidate stored users on dispatch."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, AuthorizationError, authorization_scope, current_authorization,
)
from je_auto_control.utils.rbac.users import Capability, UserStore


@dataclass(frozen=True)
class DeferredAuthorization:
    """A registered work item's authority, independent of its worker's context.

    Store-backed identities are refreshed at each dispatch. Explicit Python
    contexts without a store path retain their captured role. No context
    represents trusted local work and explicitly clears ambient worker roles.
    """

    context: Optional[AuthorizationContext] = None

    @classmethod
    def capture(cls) -> "DeferredAuthorization":
        """Capture the current caller when work is registered, not when started."""
        return cls(current_authorization())

    def _resolve(self) -> Optional[AuthorizationContext]:
        context = self.context
        if context is None or context.store_path is None:
            return context
        # A fresh store reads deletions, role changes and damaged/missing files
        # even when another process manages the users. Tokens are not retained.
        record = UserStore(Path(context.store_path)).get(context.user_id)
        if record is None:
            raise AuthorizationError(f"deferred work owner {context.user_id!r} is no longer authorised")
        return AuthorizationContext(record.user_id, record.role, store_path=context.store_path)

    @contextmanager
    def scope(self) -> Iterator[None]:
        """Run as the current registrant, refusing revoked or read-only users."""
        context = self._resolve()
        with authorization_scope(context):
            if context is not None and not context.allows(Capability.DRIVE_INPUT):
                raise AuthorizationError(
                    f"deferred work needs {Capability.DRIVE_INPUT!r}; "
                    f"user {context.user_id!r} has role {context.role!r}",
                    capability=Capability.DRIVE_INPUT,
                )
            yield
