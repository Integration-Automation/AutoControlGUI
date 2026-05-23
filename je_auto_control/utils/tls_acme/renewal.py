"""Auto-renewal scheduler for TLS certificates."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.tls_acme.keys import parse_certificate_expiry


_DEFAULT_THRESHOLD = timedelta(days=30)
_DEFAULT_CHECK_INTERVAL_S = 60 * 60  # one hour


def renewal_due(certificate_path,
                *, now: Optional[datetime] = None,
                threshold: timedelta = _DEFAULT_THRESHOLD) -> bool:
    """Return ``True`` when the cert at ``certificate_path`` should be renewed.

    A missing cert is treated as "yes, renew now" so first-time
    bootstrap doesn't need a special-case path.
    """
    target = Path(os.path.expanduser(str(certificate_path)))
    if not target.exists():
        return True
    try:
        not_after = parse_certificate_expiry(target.read_bytes())
    except (ValueError, OSError):
        return True
    reference = now or datetime.now(timezone.utc)
    return (not_after - reference) <= threshold


class RenewalScheduler:
    """Background thread that polls ``renewal_due`` and re-runs an issuer.

    The ``renew`` callable receives no arguments and is expected to
    fetch (or refresh) the certificate at ``certificate_path``. The
    scheduler doesn't care *how* — drive certbot, use the ``acme``
    library directly, or pull from a Vault PKI mount. All it does is
    answer "is it time yet?" and call the renew hook.
    """

    def __init__(self, certificate_path,
                 renew: Callable[[], None],
                 *, threshold: timedelta = _DEFAULT_THRESHOLD,
                 check_interval_s: float = _DEFAULT_CHECK_INTERVAL_S,
                 on_failure: Optional[Callable[[BaseException], None]] = None,
                 ) -> None:
        self._path = Path(os.path.expanduser(str(certificate_path)))
        self._renew = renew
        self._threshold = threshold
        self._check_interval_s = float(check_interval_s)
        self._on_failure = on_failure
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="acme-renewal", daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def tick(self) -> bool:
        """Single iteration: returns True iff a renewal was attempted."""
        if not renewal_due(self._path, threshold=self._threshold):
            return False
        try:
            self._renew()
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning(
                "acme renewal failed for %s: %r", self._path, error,
            )
            if self._on_failure is not None:
                self._on_failure(error)
            return True
        autocontrol_logger.info("acme renewal completed for %s", self._path)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            if self._stop.wait(self._check_interval_s):
                return


__all__ = ["RenewalScheduler", "renewal_due"]
