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
        # 任何續期失敗都必須路由到 on_failure 並讓輪詢繼續,絕不能拖垮
        # 續期執行緒。原本的 tuple 漏掉 certbot 的 CalledProcessError /
        # TimeoutExpired(都是 subprocess.SubprocessError,不屬 OSError/
        # ValueError/RuntimeError),所以 certbot 一失敗,acme-renewal 執行緒
        # 就無聲死亡,on_failure 從不觸發,憑證最終靜默過期。
        # Any renewal failure must route to on_failure and let the loop keep
        # polling — it must never kill the renewal thread. The previous tuple
        # missed certbot's CalledProcessError / TimeoutExpired (both
        # subprocess.SubprocessError, none an OSError/ValueError/RuntimeError),
        # so the first certbot failure killed the acme-renewal thread silently,
        # on_failure never fired, and the certificate eventually expired.
        except Exception as error:  # noqa: BLE001  # reason: see comment above
            autocontrol_logger.warning(
                "acme renewal failed for %s: %r", self._path, error,
            )
            self._invoke_on_failure(error)
            return True
        autocontrol_logger.info("acme renewal completed for %s", self._path)
        return True

    def _invoke_on_failure(self, error: BaseException) -> None:
        """Run the failure hook without ever letting it escape ``tick``.

        The hook is caller-supplied (alerting, ticketing, a pager). A raising
        hook must not propagate out of ``tick`` and kill the renewal thread —
        that would silently stop all future renewals and let the cert expire.
        """
        if self._on_failure is None:
            return
        try:
            self._on_failure(error)
        except Exception as hook_error:  # noqa: BLE001  # reason: see docstring
            autocontrol_logger.error(
                "acme renewal on_failure hook raised: %r", hook_error,
            )

    def _loop(self) -> None:
        while not self._stop.is_set():
            # Belt-and-braces: even with the hook guarded, nothing tick() might
            # raise may be allowed to kill the renewal thread.
            try:
                self.tick()
            except Exception as error:  # noqa: BLE001  # reason: see above
                autocontrol_logger.error(
                    "acme renewal tick raised: %r", error, exc_info=True,
                )
            if self._stop.wait(self._check_interval_s):
                return


__all__ = ["RenewalScheduler", "renewal_due"]
